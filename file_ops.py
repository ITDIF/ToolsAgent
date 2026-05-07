
import os
import shutil
import tempfile
import threading
import time
import subprocess
from pathlib import Path
import zipfile
import tarfile

# 可选的 rarfile 库支持
try:
    import rarfile
    RARFILE_AVAILABLE = True
except ImportError:
    RARFILE_AVAILABLE = False

from path_safety import assert_safe_write_path, PathSafetyError
from config import get_config


# 撤销栈 - 按 session_id 隔离,避免多会话相互覆盖
_UNDO_STACKS = {}
_ACTIVE_SESSION_ID = "default"
_MAX_UNDO = 50  # 单会话最大撤销步数
_UNDO_LOCK = threading.Lock()
# 批量上下文:不为 None 时,新写操作的 undo 记录会追加到此 list 而非主栈
_BATCH_CONTEXT = threading.local()


def set_active_session(session_id):
    """切换当前活动撤销栈所属会话"""
    global _ACTIVE_SESSION_ID
    with _UNDO_LOCK:
        _ACTIVE_SESSION_ID = session_id or "default"


def get_active_session():
    """返回当前活动会话 ID"""
    return _ACTIVE_SESSION_ID


def _active_stack():
    """返回当前活动会话对应的撤销栈,缺失则创建"""
    return _UNDO_STACKS.setdefault(_ACTIVE_SESSION_ID, [])


def get_undo_stack():
    """获取当前活动会话的撤销栈快照"""
    with _UNDO_LOCK:
        return list(_active_stack())


def clear_undo_stack(session_id=None):
    """清空指定(默认当前活动)会话的撤销栈,回收备份"""
    with _UNDO_LOCK:
        sid = session_id or _ACTIVE_SESSION_ID
        stack = _UNDO_STACKS.get(sid, [])
        for action in stack:
            _cleanup_action_backup(action)
        if sid in _UNDO_STACKS:
            _UNDO_STACKS[sid] = []


def clear_all_undo_stacks():
    """清空所有会话的撤销栈(主要给测试用)"""
    with _UNDO_LOCK:
        for sid, stack in list(_UNDO_STACKS.items()):
            for action in stack:
                _cleanup_action_backup(action)
        _UNDO_STACKS.clear()


def cleanup_old_backups(max_age_hours=24):
    """清理超过 max_age_hours 的临时备份目录(toolsagent_backup_*)"""
    tmpdir = Path(tempfile.gettempdir())
    cutoff = time.time() - max_age_hours * 3600
    count = 0
    for p in tmpdir.glob("toolsagent_backup_*"):
        try:
            if p.is_dir() and p.stat().st_mtime < cutoff:
                shutil.rmtree(p, ignore_errors=True)
                count += 1
        except Exception:
            pass
    return count


def _cleanup_action_backup(action):
    """删除 action 占用的所有备份临时目录"""
    if not isinstance(action, dict):
        return
    # 旧字段: action["backup"] 直接指向 backup_path
    backup = action.get("backup")
    if backup:
        try:
            shutil.rmtree(Path(backup).parent, ignore_errors=True)
        except Exception:
            pass
    # 新字段: action["dst_snap"] / action["snap"] 内嵌 snapshot
    for key in ("dst_snap", "snap"):
        snap = action.get(key)
        if snap:
            _cleanup_snapshot(snap)
    # 批量类型: 递归清理 sub_actions
    if action.get("type") == "batch":
        for sub in action.get("sub_actions", []) or []:
            _cleanup_action_backup(sub)


def _push_undo(action):
    """添加撤销操作。若处于批量上下文则追加到批量 sub_actions,否则进当前活动会话栈"""
    sub_actions = getattr(_BATCH_CONTEXT, "sub_actions", None)
    if sub_actions is not None:
        sub_actions.append(action)
        return
    with _UNDO_LOCK:
        stack = _active_stack()
        stack.append(action)
        while len(stack) > _MAX_UNDO:
            old = stack.pop(0)
            _cleanup_action_backup(old)


def _describe_action(action):
    """生成单条 undo 记录的人类可读描述"""
    t = action.get("type")
    if t == "delete":
        return f"删除 {action.get('path')}"
    if t == "move":
        return f"移动 {action.get('src')} -> {action.get('dst')}"
    if t == "rename":
        return f"重命名 {action.get('src')} -> {action.get('dst')}"
    if t == "write_target":
        op = action.get("op") or "写入"
        return f"{op} {action.get('path')}"
    if t == "append_truncate":
        return f"追加写入 {action.get('path')}"
    if t == "copy":
        return f"复制 {action.get('src')} -> {action.get('dst')}"
    if t == "extract":
        return f"解压 {action.get('archive_path')} -> {action.get('output_path')}"
    if t == "create_archive":
        srcs = action.get('source_paths', [])
        if len(srcs) == 1:
            return f"压缩 {srcs[0]} -> {action.get('archive_path')}"
        else:
            return f"压缩 {len(srcs)} 个文件 -> {action.get('archive_path')}"
    if t == "batch":
        subs = action.get("sub_actions", [])
        label = action.get("label") or f"批量操作({len(subs)} 步)"
        return label
    # 兼容老格式(write/create_file/create_folder)
    if t == "write":
        return f"覆盖写入 {action.get('path')}"
    if t == "create_file":
        return f"创建文件 {action.get('path')}"
    if t == "create_folder":
        return f"创建文件夹 {action.get('path')}"
    return f"未知操作({t})"


def get_undo_history(limit=20):
    """返回当前活动会话撤销栈描述,最近的操作排在前面"""
    with _UNDO_LOCK:
        snapshot = list(_active_stack())
    items = []
    for idx, action in enumerate(reversed(snapshot[-limit:]), start=1):
        items.append({
            "index": idx,
            "type": action.get("type"),
            "description": _describe_action(action),
        })
    return {"success": True, "count": len(snapshot), "items": items}


def _backup_file(path):
    """备份单个文件到临时目录，返回备份路径"""
    path = Path(path)
    if not path.exists():
        return None
    backup_dir = Path(tempfile.mkdtemp(prefix="toolsagent_backup_"))
    backup_path = backup_dir / path.name
    if path.is_file():
        shutil.copy2(path, backup_path)
    else:
        shutil.copytree(path, backup_path)
    return str(backup_path)


def _capture_target_state(path):
    """捕获目标路径写入前的状态,用于事后构造可逆 undo

    返回 {"existed": bool, "is_dir": bool, "backup": str|None}
    若 existed=False, backup=None;否则 backup 指向临时备份(由 caller 负责清理或交给 undo 流程清理)
    """
    p = Path(path)
    if not p.exists():
        return {"existed": False, "is_dir": False, "backup": None}
    return {
        "existed": True,
        "is_dir": p.is_dir(),
        "backup": _backup_file(path),
    }


def _remove_target(path):
    """统一删除文件或文件夹(用于 undo 内部)"""
    p = Path(path)
    if not p.exists() and not p.is_symlink():
        return
    if p.is_file() or p.is_symlink():
        p.unlink()
    else:
        shutil.rmtree(p)


def _restore_target(path, snapshot):
    """按 snapshot 把 path 还原回写操作前的状态"""
    if not snapshot:
        return
    _remove_target(path)
    if snapshot.get("existed") and snapshot.get("backup"):
        bk = Path(snapshot["backup"])
        if not bk.exists():
            return
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if snapshot.get("is_dir"):
            shutil.copytree(bk, target)
        else:
            shutil.copy2(bk, target)
        shutil.rmtree(bk.parent, ignore_errors=True)


def _cleanup_snapshot(snapshot):
    """释放 snapshot 占用的备份目录(undo 前用)"""
    if not snapshot:
        return
    bk = snapshot.get("backup")
    if bk:
        try:
            shutil.rmtree(Path(bk).parent, ignore_errors=True)
        except Exception:
            pass


def _apply_undo_action(action):
    """对单个 action 执行撤销;成功返回 (True, message),失败返回 (False, error)"""
    try:
        action_type = action["type"]
        if action_type == "delete":
            backup_path = action.get("backup")
            target_path = action["path"]
            if backup_path and Path(backup_path).exists():
                shutil.move(backup_path, target_path)
                _cleanup_action_backup(action)
                return True, f"已恢复: {target_path}"
            return False, f"备份缺失,无法恢复: {target_path}"
        if action_type == "move":
            # 1) 把当前 dst 移回 src
            shutil.move(action["dst"], action["src"])
            # 2) 若 dst 原本存在,恢复其旧内容
            dst_snap = action.get("dst_snap")
            if dst_snap and dst_snap.get("existed"):
                _restore_target(action["dst"], dst_snap)
            return True, f"已撤销移动: {action['dst']} -> {action['src']}"
        if action_type == "rename":
            Path(action["dst"]).rename(action["src"])
            dst_snap = action.get("dst_snap")
            if dst_snap and dst_snap.get("existed"):
                _restore_target(action["dst"], dst_snap)
            return True, f"已撤销重命名: {action['dst']} -> {action['src']}"
        if action_type == "copy":
            # 把当前 dst 移除,并(若有)恢复原 dst
            dst_snap = action.get("dst_snap")
            if dst_snap is None:
                # 老格式: dst 当时不存在,直接删
                _remove_target(action["dst"])
            else:
                _restore_target(action["dst"], dst_snap)
            return True, f"已撤销复制到: {action['dst']}"
        if action_type == "extract":
            # 把当前输出目录移除,并(若有)恢复原目录
            dst_snap = action.get("dst_snap")
            if dst_snap is None:
                # 当时不存在,直接删
                _remove_target(action["output_path"])
            else:
                _restore_target(action["output_path"], dst_snap)
            return True, f"已撤销解压: {action['output_path']}"
        if action_type == "create_archive":
            # 把当前压缩文件移除,并(若有)恢复原文件
            dst_snap = action.get("dst_snap")
            if dst_snap is None:
                # 当时不存在,直接删
                _remove_target(action["archive_path"])
            else:
                _restore_target(action["archive_path"], dst_snap)
            return True, f"已撤销压缩: {action['archive_path']}"
        if action_type == "write_target":
            # 统一的写入撤销:create_file/write_file 都走这里
            _restore_target(action["path"], action.get("snap"))
            label = action.get("op") or "写入"
            return True, f"已撤销{label}: {action['path']}"
        if action_type == "append_truncate":
            # 追加撤销:截回原长度,或删除新建文件
            target = Path(action["path"])
            if not action.get("existed"):
                target.unlink(missing_ok=True)
                return True, f"已撤销追加(删除新建文件): {action['path']}"
            with open(target, "rb+") as f:
                f.truncate(int(action.get("prev_size", 0)))
            return True, f"已撤销追加: {action['path']}"
        if action_type == "batch":
            sub_actions = list(action.get("sub_actions", []))
            sub_results = []
            all_ok = True
            for sub in reversed(sub_actions):
                ok, msg = _apply_undo_action(sub)
                sub_results.append({"success": ok, "message": msg})
                if not ok:
                    all_ok = False
            label = action.get("label") or f"批量操作({len(sub_actions)} 步)"
            return all_ok, {
                "label": label,
                "sub_results": sub_results,
            }
        # ----- 兼容老的 action 类型(在迁移期保留) -----
        if action_type == "write":
            backup_path = action.get("backup")
            target_path = action["path"]
            if backup_path and Path(backup_path).exists():
                shutil.copy2(backup_path, target_path)
                _cleanup_action_backup(action)
                return True, f"已恢复文件: {target_path}"
            return False, f"备份缺失,无法恢复: {target_path}"
        if action_type == "create_file":
            Path(action["path"]).unlink(missing_ok=True)
            return True, f"已删除创建的文件: {action['path']}"
        if action_type == "create_folder":
            folder = Path(action["path"])
            if folder.exists():
                shutil.rmtree(folder)
            return True, f"已删除创建的文件夹: {action['path']}"
        return False, f"未知的撤销操作类型: {action_type}"
    except Exception as e:
        return False, f"撤销失败: {str(e)}"


def undo_last(count=1):
    """撤销最近 count 次操作（默认 1 次）。返回每一步的撤销结果"""
    try:
        count = int(count)
    except (TypeError, ValueError):
        return {"success": False, "error": "count 必须是正整数"}
    if count < 1:
        return {"success": False, "error": "count 必须 >= 1"}

    results = []
    failures = 0
    for _ in range(count):
        with _UNDO_LOCK:
            stack = _active_stack()
            if not stack:
                break
            action = stack.pop()
        ok, payload = _apply_undo_action(action)
        if not ok:
            # 失败时保留剩余记录,不放回栈(放回会导致重复触发同样错误)
            failures += 1
            results.append({"success": False, "error": payload, "type": action.get("type")})
            break
        results.append({"success": True, "message": payload, "type": action.get("type")})

    if not results:
        return {"success": False, "error": "没有可撤销的操作"}

    return {
        "success": failures == 0,
        "undone": len(results) - failures,
        "results": results,
    }


def _safety_check(*paths):
    """对一组待写入路径做安全校验,通过返回 None,失败返回标准错误响应"""
    cfg = get_config()
    for p in paths:
        try:
            assert_safe_write_path(p, cfg)
        except PathSafetyError as e:
            return {"success": False, "error": str(e)}
    return None


def move_file(src, dst):
    """移动文件或文件夹"""
    src_path = Path(src)
    dst_path = Path(dst)

    if not src_path.exists():
        return {"success": False, "error": f"源路径不存在: {src}"}

    err = _safety_check(src, dst)
    if err:
        return err

    dst_snap = _capture_target_state(dst)
    try:
        shutil.move(str(src_path), str(dst_path))
        _push_undo({
            "type": "move",
            "src": src,
            "dst": dst,
            "dst_snap": dst_snap,
        })
        return {"success": True, "message": f"已移动: {src} -> {dst}"}
    except Exception as e:
        _cleanup_snapshot(dst_snap)
        return {"success": False, "error": str(e)}


def copy_file(src, dst):
    """复制文件或文件夹"""
    src_path = Path(src)
    dst_path = Path(dst)

    if not src_path.exists():
        return {"success": False, "error": f"源路径不存在: {src}"}

    err = _safety_check(dst)
    if err:
        return err

    dst_snap = _capture_target_state(dst)
    try:
        if dst_snap["existed"]:
            # shutil.copytree 不允许覆盖,先清空 dst 再复制
            _remove_target(dst)
        if src_path.is_file():
            shutil.copy2(str(src_path), str(dst_path))
        else:
            shutil.copytree(str(src_path), str(dst_path))
        _push_undo({
            "type": "copy",
            "src": src,
            "dst": dst,
            "dst_snap": dst_snap,
        })
        return {"success": True, "message": f"已复制: {src} -> {dst}"}
    except Exception as e:
        # 失败时尽力还原
        _restore_target(dst, dst_snap)
        return {"success": False, "error": str(e)}


def delete_file(path):
    """删除文件或文件夹"""
    file_path = Path(path)

    if not file_path.exists():
        return {"success": False, "error": f"路径不存在: {path}"}

    err = _safety_check(path)
    if err:
        return err

    try:
        # 备份被删除的文件/文件夹
        backup_path = _backup_file(path)
        if file_path.is_file():
            file_path.unlink()
        else:
            shutil.rmtree(str(file_path))
        _push_undo({
            "type": "delete",
            "path": path,
            "backup": backup_path
        })
        return {"success": True, "message": f"已删除: {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def extract_archive(archive_path, output_path=None):
    """解压压缩文件（支持 zip, tar, tar.gz, tar.bz2, rar）"""
    archive_p = Path(archive_path)

    if not archive_p.exists():
        return {"success": False, "error": f"压缩文件不存在: {archive_path}"}

    if not archive_p.is_file():
        return {"success": False, "error": f"不是文件: {archive_path}"}

    # 确定输出路径
    if output_path is None:
        # 默认解压到同名文件夹
        output_path = str(archive_p.parent / archive_p.stem)

    # 输出路径安全校验
    err = _safety_check(output_path)
    if err:
        return err

    # 检查输出目录是否存在并备份
    dst_snap = _capture_target_state(output_path)
    extracted_paths = []

    try:
        output_p = Path(output_path)
        output_p.mkdir(parents=True, exist_ok=True)

        ext = archive_p.suffix.lower()

        if ext == ".zip":
            with zipfile.ZipFile(archive_p, "r") as zf:
                zf.extractall(output_p)
                extracted_paths = [str(output_p / name) for name in zf.namelist()]
        elif ext == ".rar":
            if not RARFILE_AVAILABLE:
                _cleanup_snapshot(dst_snap)
                return {"success": False, "error": "RAR 文件支持需要安装 rarfile 库: pip install rarfile"}
            try:
                with rarfile.RarFile(archive_p, "r") as rf:
                    rf.extractall(output_p)
                    extracted_paths = [str(output_p / name) for name in rf.namelist()]
            except rarfile.RarCannotExec:
                _cleanup_snapshot(dst_snap)
                return {"success": False, "error": "需要安装 unrar/rar 命令行工具才能解压 RAR 文件"}
        elif ext in (".tar", ".gz", ".bz2", ".tgz"):
            mode = "r"
            if ext == ".gz":
                mode = "r:gz"
            elif ext == ".bz2":
                mode = "r:bz2"
            elif ext == ".tgz":
                mode = "r:gz"
            with tarfile.open(archive_p, mode) as tf:
                tf.extractall(output_p)
                extracted_paths = [str(output_p / name) for name in tf.getnames()]
        else:
            _cleanup_snapshot(dst_snap)
            supported = ".zip, .tar, .tar.gz, .tgz, .tar.bz2, .rar"
            return {"success": False, "error": f"不支持的压缩格式: {ext}。支持的格式: {supported}"}

        _push_undo({
            "type": "extract",
            "archive_path": archive_path,
            "output_path": output_path,
            "dst_snap": dst_snap
        })
        return {"success": True, "message": f"已解压: {archive_path} -> {output_path}"}
    except Exception as e:
        # 尽力恢复
        _restore_target(output_path, dst_snap)
        return {"success": False, "error": str(e)}


def _find_rar_executable():
    """查找系统中的 RAR 可执行文件路径。

    搜索顺序:
    1. config.json 中的 rar_executable 配置
    2. PATH 环境变量中的 rar/rar.exe
    3. 常见 Windows 安装路径 (Program Files/WinRAR)

    返回可执行文件完整路径，未找到返回 None。
    """
    cfg = get_config()

    # 1. 检查配置中的自定义路径
    configured = cfg.get("rar_executable")
    if configured and Path(configured).exists():
        return str(Path(configured).resolve())

    # 2. 检查 PATH 中的命令
    for cmd in ["rar", "rar.exe"]:
        if shutil.which(cmd):
            return shutil.which(cmd)

    # 3. 搜索常见 Windows 安装路径
    common_paths = [
        r"C:\Program Files\WinRAR\rar.exe",
        r"C:\Program Files (x86)\WinRAR\rar.exe",
        r"C:\Program Files\WinRAR\WinRAR.exe",
        r"C:\Program Files (x86)\WinRAR\WinRAR.exe",
    ]
    for p in common_paths:
        if Path(p).exists():
            return p

    return None


def create_archive(source_paths, archive_path, format=None):
    """创建压缩文件（支持 zip, tar, tar.gz, tar.bz2, tgz, rar）

    source_paths: 单个路径或路径列表
    archive_path: 输出压缩文件路径
    format: 压缩格式（zip, tar, gz, bz2, tgz, rar），默认根据文件后缀推断
    """
    if isinstance(source_paths, str):
        source_paths = [source_paths]

    # 校验所有源路径存在
    for path in source_paths:
        if not Path(path).exists():
            return {"success": False, "error": f"源路径不存在: {path}"}

    # 确定压缩格式
    archive_p = Path(archive_path)
    if format is None:
        ext = archive_p.suffix.lower()
        # 处理双扩展名
        if len(archive_p.suffixes) >= 2:
            ext2 = archive_p.suffixes[-2].lower()
            if ext2 == ".tar":
                ext = ext2 + ext
    else:
        ext = "." + format.lower()

    # 输出文件安全校验
    err = _safety_check(archive_path)
    if err:
        return err

    # 备份目标文件状态，用于撤销
    dst_snap = _capture_target_state(archive_path)

    try:
        # 确保输出目录存在
        archive_p.parent.mkdir(parents=True, exist_ok=True)

        if ext in (".zip"):
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for src_path in source_paths:
                    src_p = Path(src_path)
                    if src_p.is_file():
                        # 单个文件压缩
                        zf.write(src_p, src_p.name)
                    else:
                        # 文件夹递归压缩
                        for root, _, files in os.walk(src_p):
                            root_p = Path(root)
                            # 计算相对于 src_p 的相对路径
                            rel_root = root_p.relative_to(src_p)
                            for file in files:
                                file_path = root_p / file
                                arcname = rel_root / file
                                zf.write(file_path, arcname)
        elif ext in (".tar", ".tar.gz", ".tar.bz2", ".tgz"):
            mode = "w"
            if ext in (".tar.gz", ".tgz"):
                mode = "w:gz"
            elif ext == ".tar.bz2":
                mode = "w:bz2"
            with tarfile.open(archive_path, mode) as tf:
                for src_path in source_paths:
                    src_p = Path(src_path)
                    # 对每个源使用其 basename 作为压缩文件中的根路径
                    tf.add(src_p, arcname=src_p.name)
        elif ext == ".rar":
            rar_cmd = _find_rar_executable()
            if rar_cmd is None:
                _cleanup_snapshot(dst_snap)
                return {
                    "success": False,
                    "error": "未找到 RAR/WinRAR 工具。"
                             "请安装 WinRAR 并确保 rar.exe 在系统 PATH 中，"
                             "或在 config.json 中设置 rar_executable 路径。"
                }

            # 准备命令参数
            cmd_args = [rar_cmd, "a", "-ep1"]  # -ep1 保留相对路径
            if os.path.exists(archive_path):
                cmd_args.append("-o+")  # 覆盖现有文件
            cmd_args.append(archive_path)

            # 添加源路径
            for src_path in source_paths:
                cmd_args.append(src_path)

            # 执行压缩
            result = subprocess.run(cmd_args, capture_output=True, text=True)

            if result.returncode != 0:
                _cleanup_snapshot(dst_snap)
                error_msg = result.stderr.strip() if result.stderr else result.stdout.strip()
                return {"success": False, "error": f"RAR 压缩失败: {error_msg}"}
        else:
            _cleanup_snapshot(dst_snap)
            supported = ".zip, .tar, .tar.gz, .tgz, .tar.bz2, .rar"
            return {"success": False, "error": f"不支持的压缩格式: {ext}。支持的格式: {supported}"}

        # 添加入撤销栈
        _push_undo({
            "type": "create_archive",
            "source_paths": source_paths,
            "archive_path": archive_path,
            "dst_snap": dst_snap
        })

        return {"success": True, "message": f"已创建压缩文件: {archive_path}"}
    except Exception as e:
        # 出错时恢复
        _restore_target(archive_path, dst_snap)
        return {"success": False, "error": str(e)}


def create_folder(path):
    """创建文件夹"""
    folder_path = Path(path)

    err = _safety_check(path)
    if err:
        return err

    try:
        existed = folder_path.exists()
        folder_path.mkdir(parents=True, exist_ok=True)
        if not existed:
            _push_undo({
                "type": "write_target",
                "path": path,
                "op": "创建文件夹",
                "snap": {"existed": False, "is_dir": False, "backup": None},
            })
        return {"success": True, "message": f"已创建文件夹: {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_file(path, content=""):
    """创建文件,可指定内容。若目标已存在则备份原内容,撤销时可还原"""
    file_path = Path(path)

    err = _safety_check(path)
    if err:
        return err

    snap = _capture_target_state(path)
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        _push_undo({
            "type": "write_target",
            "path": path,
            "op": "覆盖创建" if snap["existed"] else "创建文件",
            "snap": snap,
        })
        msg = "已覆盖创建" if snap["existed"] else "已创建文件"
        return {"success": True, "message": f"{msg}: {path}"}
    except Exception as e:
        _cleanup_snapshot(snap)
        return {"success": False, "error": str(e)}


def read_file(path):
    """读取文件内容"""
    file_path = Path(path)

    if not file_path.exists():
        return {"success": False, "error": f"路径不存在: {path}"}
    if not file_path.is_file():
        return {"success": False, "error": f"路径不是文件: {path}"}

    cfg = get_config()
    max_bytes = int(cfg.get("max_read_bytes", 1024 * 1024))

    try:
        size = file_path.stat().st_size
        with open(file_path, "rb") as f:
            data = f.read(max_bytes)
        content = data.decode("utf-8", errors="replace")
        return {
            "success": True,
            "path": path,
            "content": content,
            "truncated": size > max_bytes,
            "bytes_read": len(data),
            "total_bytes": size,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def write_file(path, content, append=False):
    """写入文件内容,支持覆盖或追加。两种模式都支持撤销:
    - 覆盖: 备份原内容,撤销时还原(若文件原本不存在,撤销时直接删除)
    - 追加: 记录原文件长度,撤销时截断到原长度(若文件原本不存在,撤销时删除)
    """
    file_path = Path(path)

    err = _safety_check(path)
    if err:
        return err

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if append:
            existed = file_path.exists()
            prev_size = file_path.stat().st_size if existed else 0
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(content)
            _push_undo({
                "type": "append_truncate",
                "path": path,
                "existed": existed,
                "prev_size": prev_size,
            })
            return {"success": True, "message": f"已追加文件: {path}"}
        snap = _capture_target_state(path)
        try:
            file_path.write_text(content, encoding="utf-8")
        except Exception:
            _cleanup_snapshot(snap)
            raise
        _push_undo({
            "type": "write_target",
            "path": path,
            "op": "覆盖写入" if snap["existed"] else "新建写入",
            "snap": snap,
        })
        return {"success": True, "message": f"已覆盖文件: {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def rename_file(src, dst):
    """重命名文件或文件夹"""
    src_path = Path(src)
    dst_path = Path(dst)

    if not src_path.exists():
        return {"success": False, "error": f"源路径不存在: {src}"}

    err = _safety_check(src, dst)
    if err:
        return err

    dst_snap = _capture_target_state(dst)
    try:
        # POSIX 下 Path.rename 会原子覆盖目标,先备份后再 rename;
        # Windows 下若 dst 已存在会抛 FileExistsError,清掉 dst 之后再 rename
        if dst_snap["existed"]:
            _remove_target(dst)
        src_path.rename(dst_path)
        _push_undo({
            "type": "rename",
            "src": src,
            "dst": dst,
            "dst_snap": dst_snap,
        })
        return {"success": True, "message": f"已重命名: {src} -> {dst}"}
    except Exception as e:
        # 失败时尝试还原 dst 原内容
        _restore_target(dst, dst_snap)
        return {"success": False, "error": str(e)}


def search_files(pattern, path=".", search_type="all"):
    """搜索文件/文件夹，支持按名称匹配"""
    dir_path = Path(path)

    if not dir_path.exists():
        return {"success": False, "error": f"路径不存在: {path}"}

    cfg = get_config()
    max_results = int(cfg.get("max_search_results", 100))
    max_depth = int(cfg.get("max_search_depth", 10))
    tool_timeout = float(cfg.get("tool_timeout", 30))
    base_depth = len(dir_path.resolve().parts)

    try:
        results = []
        truncated = False
        pattern_lower = pattern.lower()
        start_time = time.time()

        for root, dirs, files in os.walk(dir_path):
            if time.time() - start_time > tool_timeout:
                truncated = True
                break

            cur_depth = len(Path(root).resolve().parts) - base_depth
            if cur_depth >= max_depth:
                # 达到深度上限,不再继续向下
                dirs[:] = []

            candidates = []
            if search_type in ("all", "folder"):
                candidates.extend((d, True) for d in dirs)
            if search_type in ("all", "file"):
                candidates.extend((f, False) for f in files)

            for name, is_dir in candidates:
                if pattern_lower in name.lower():
                    results.append({
                        "name": name,
                        "type": "folder" if is_dir else "file",
                        "path": str(Path(root) / name)
                    })
                    if len(results) >= max_results:
                        truncated = True
                        break
            if truncated:
                break

        return {
            "success": True,
            "results": results,
            "path": path,
            "pattern": pattern,
            "truncated": truncated,
            "max_results": max_results,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_files(path="."):
    """列出指定目录下的文件"""
    dir_path = Path(path)

    if not dir_path.exists():
        return {"success": False, "error": f"路径不存在: {path}"}

    try:
        files = []
        for item in dir_path.iterdir():
            files.append({
                "name": item.name,
                "type": "folder" if item.is_dir() else "file",
                "path": str(item)
            })
        return {"success": True, "files": files, "path": path}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _human_size(size_bytes):
    """将字节数转为人类可读字符串"""
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    for unit in units:
        if abs(size) < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


def scan_disk(path=".", max_depth=None, max_results=None, min_size=0):
    """扫描目录并统计各子文件夹大小,返回按大小降序排列的结果"""
    dir_path = Path(path)

    if not dir_path.exists():
        return {"success": False, "error": f"路径不存在: {path}"}

    cfg = get_config()
    max_depth = int(max_depth if max_depth is not None else cfg.get("max_search_depth", 10))
    max_results = int(max_results if max_results is not None else cfg.get("max_search_results", 100))
    tool_timeout = float(cfg.get("tool_timeout", 30))
    min_size = int(min_size)

    base = str(dir_path.resolve())
    base_depth = len(dir_path.resolve().parts)
    sizes = {}
    truncated = False
    start_time = time.time()

    try:
        for root, dirs, files in os.walk(base):
            if time.time() - start_time > tool_timeout:
                truncated = True
                break

            cur_depth = len(Path(root).resolve().parts) - base_depth
            if cur_depth >= max_depth:
                dirs[:] = []
                continue

            root_size = 0
            for f in files:
                fp = os.path.join(root, f)
                try:
                    root_size += os.path.getsize(fp)
                except Exception:
                    pass

            sizes[root] = sizes.get(root, 0) + root_size

            # 将当前目录大小累加到所有祖先目录
            parent = root
            while True:
                parent = os.path.dirname(parent)
                if not parent or len(parent) < len(base):
                    break
                sizes[parent] = sizes.get(parent, 0) + root_size

        items = [
            {
                "path": p,
                "size_bytes": s,
                "size_human": _human_size(s),
            }
            for p, s in sizes.items()
            if s >= min_size
        ]
        items.sort(key=lambda x: x["size_bytes"], reverse=True)

        truncated_by_results = len(items) > max_results
        if truncated_by_results:
            items = items[:max_results]

        return {
            "success": True,
            "path": path,
            "items": items,
            "truncated": truncated or truncated_by_results,
            "count": len(items),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# 允许在 batch_operations 内部调用的工具(写操作 + 只读读取)
_BATCH_ALLOWED_TOOLS = {
    "move_file", "copy_file", "delete_file",
    "create_folder", "create_file",
    "write_file", "rename_file",
    "read_file", "list_files", "search_files",
    "extract_archive", "create_archive",
}


def batch_operations(operations, stop_on_error=True, label=None):
    """批量执行多个文件操作,作为一个整体进入撤销栈。

    operations: [{"tool": "...", "arguments": {...}}]
    stop_on_error: True 则首个失败就中断后续步骤;False 则尽力执行所有步骤
    label: 撤销历史中显示的标签
    返回每一步的结果,以及整体成功/失败标志
    """
    if not isinstance(operations, list) or not operations:
        return {"success": False, "error": "operations 必须是非空数组"}

    # 嵌套调用直接拒绝,避免歧义
    if getattr(_BATCH_CONTEXT, "sub_actions", None) is not None:
        return {"success": False, "error": "不允许嵌套 batch_operations"}

    sub_actions = []
    _BATCH_CONTEXT.sub_actions = sub_actions
    results = []
    failures = 0
    halted_index = None

    try:
        for i, op in enumerate(operations):
            if not isinstance(op, dict):
                results.append({"index": i, "success": False, "error": "operation 必须是对象"})
                failures += 1
                if stop_on_error:
                    halted_index = i
                    break
                continue

            tool_name = op.get("tool")
            tool_args = op.get("arguments") or {}
            if tool_name not in _BATCH_ALLOWED_TOOLS:
                results.append({
                    "index": i, "tool": tool_name,
                    "success": False, "error": f"工具 {tool_name} 不允许在批量中调用"
                })
                failures += 1
                if stop_on_error:
                    halted_index = i
                    break
                continue
            if not isinstance(tool_args, dict):
                results.append({
                    "index": i, "tool": tool_name,
                    "success": False, "error": "arguments 必须是对象"
                })
                failures += 1
                if stop_on_error:
                    halted_index = i
                    break
                continue

            try:
                step_result = TOOL_REGISTRY[tool_name](**tool_args)
            except TypeError as e:
                step_result = {"success": False, "error": f"参数错误: {e}"}
            except Exception as e:
                step_result = {"success": False, "error": str(e)}

            entry = {"index": i, "tool": tool_name, "result": step_result,
                     "success": bool(step_result.get("success"))}
            results.append(entry)
            if not entry["success"]:
                failures += 1
                if stop_on_error:
                    halted_index = i
                    break
    finally:
        _BATCH_CONTEXT.sub_actions = None

    # 仅当至少有一步成功且产生了 sub_action 时才入栈
    if sub_actions:
        _push_undo({
            "type": "batch",
            "label": label or f"批量操作({len(sub_actions)} 步)",
            "sub_actions": sub_actions,
        })

    return {
        "success": failures == 0,
        "total": len(operations),
        "executed": len(results),
        "failures": failures,
        "halted_at": halted_index,
        "results": results,
    }


TOOL_REGISTRY = {
    "move_file": move_file,
    "copy_file": copy_file,
    "delete_file": delete_file,
    "create_folder": create_folder,
    "create_file": create_file,
    "read_file": read_file,
    "write_file": write_file,
    "rename_file": rename_file,
    "search_files": search_files,
    "list_files": list_files,
    "scan_disk": scan_disk,
    "extract_archive": extract_archive,
    "create_archive": create_archive,
    "undo_last": undo_last,
    "undo_history": get_undo_history,
    "batch_operations": batch_operations,
}


TOOL_SCHEMAS = [
    {
        "name": "undo_last",
        "description": "撤销最近的文件操作。可通过 count 一次撤销多步;批量操作算一步整体撤销",
        "input_schema": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "撤销步数,默认 1", "minimum": 1}
            },
            "required": []
        }
    },
    {
        "name": "undo_history",
        "description": "查看撤销栈,列出可撤销的最近操作(最近的排在第一位)",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "返回最近多少条,默认 20", "minimum": 1}
            },
            "required": []
        }
    },
    {
        "name": "batch_operations",
        "description": "批量执行多个文件操作,作为一个整体可一次撤销。适合需要一次完成多个相关写操作的场景(如整理目录、批量改名)。允许的子工具: move_file/copy_file/delete_file/create_folder/create_file/write_file/rename_file/read_file/list_files/search_files。",
        "input_schema": {
            "type": "object",
            "properties": {
                "operations": {
                    "type": "array",
                    "description": "操作列表,按顺序执行",
                    "items": {
                        "type": "object",
                        "properties": {
                            "tool": {"type": "string", "description": "子工具名"},
                            "arguments": {"type": "object", "description": "子工具参数"}
                        },
                        "required": ["tool", "arguments"]
                    }
                },
                "stop_on_error": {
                    "type": "boolean",
                    "description": "首个失败步骤是否中断后续步骤,默认 true"
                },
                "label": {"type": "string", "description": "撤销历史显示的标签(可选)"}
            },
            "required": ["operations"]
        }
    },
    {
        "name": "move_file",
        "description": "移动文件或文件夹从源路径到目标路径",
        "input_schema": {
            "type": "object",
            "properties": {
                "src": {"type": "string", "description": "源文件或文件夹路径"},
                "dst": {"type": "string", "description": "目标路径"}
            },
            "required": ["src", "dst"]
        }
    },
    {
        "name": "copy_file",
        "description": "复制文件或文件夹",
        "input_schema": {
            "type": "object",
            "properties": {
                "src": {"type": "string", "description": "源文件或文件夹路径"},
                "dst": {"type": "string", "description": "目标路径"}
            },
            "required": ["src", "dst"]
        }
    },
    {
        "name": "delete_file",
        "description": "删除文件或文件夹（危险操作，需谨慎）",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要删除的文件或文件夹路径"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "create_folder",
        "description": "创建文件夹，会自动创建不存在的父目录",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要创建的文件夹路径"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "create_file",
        "description": "创建文件，可指定文件内容，会自动创建不存在的父目录",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要创建的文件路径"},
                "content": {"type": "string", "description": "文件内容，默认为空"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "read_file",
        "description": "读取文件内容",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要读取的文件路径"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "写入文件内容，支持覆盖或追加模式",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要写入的文件路径"},
                "content": {"type": "string", "description": "要写入的文件内容"},
                "append": {"type": "boolean", "description": "是否追加模式，默认为 false（覆盖）"}
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "rename_file",
        "description": "重命名文件或文件夹",
        "input_schema": {
            "type": "object",
            "properties": {
                "src": {"type": "string", "description": "源文件或文件夹路径"},
                "dst": {"type": "string", "description": "新名称或新路径"}
            },
            "required": ["src", "dst"]
        }
    },
    {
        "name": "search_files",
        "description": "搜索文件或文件夹，支持按名称匹配模式",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "搜索起始目录，默认为当前目录"},
                "pattern": {"type": "string", "description": "搜索关键词/模式"},
                "search_type": {"type": "string", "description": "搜索类型：all（全部）、file（仅文件）、folder（仅文件夹），默认为 all", "enum": ["all", "file", "folder"]}
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "list_files",
        "description": "列出指定目录下的文件和文件夹",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目录路径，默认为当前目录"}
            }
        }
    },
    {
        "name": "scan_disk",
        "description": "扫描目录并统计各子文件夹大小，返回按大小降序排列的结果",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "扫描起始目录，默认为当前目录"},
                "max_depth": {"type": "integer", "description": "最大递归深度，默认读取配置 max_search_depth"},
                "max_results": {"type": "integer", "description": "返回结果最大数量，默认读取配置 max_search_results"},
                "min_size": {"type": "integer", "description": "最小字节数过滤，默认 0"}
            }
        }
    },
    {
        "name": "extract_archive",
        "description": "解压压缩文件，支持 zip、tar、tar.gz、tgz、tar.bz2、rar 格式。默认解压到同名文件夹",
        "input_schema": {
            "type": "object",
            "properties": {
                "archive_path": {"type": "string", "description": "压缩文件路径"},
                "output_path": {"type": "string", "description": "解压目标路径（可选，默认解压到与压缩文件同名的文件夹）"}
            },
            "required": ["archive_path"]
        }
    },
    {
        "name": "create_archive",
        "description": "创建压缩文件，支持 zip、tar、tar.gz、tgz、tar.bz2、rar 格式。可以压缩单个文件或多个文件/文件夹",
        "input_schema": {
            "type": "object",
            "properties": {
                "source_paths": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}}
                    ],
                    "description": "要压缩的文件或文件夹路径（单个路径字符串或路径数组）"
                },
                "archive_path": {"type": "string", "description": "输出压缩文件路径"},
                "format": {"type": "string", "description": "压缩格式（可选：zip, tar, gz, bz2, tgz, rar），默认根据文件后缀推断"}
            },
            "required": ["source_paths", "archive_path"]
        }
    }
]

