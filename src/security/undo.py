import os
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
# 兼容Windows和Unix的文件锁
try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    # Windows 平台
    import msvcrt
    HAS_FCNTL = False

from ..infra.constants import UndoConstants

logger = __import__("logging").getLogger(__name__)


class UndoActionType:
    """撤销操作类型常量"""
    DELETE = "delete"
    MOVE = "move"
    RENAME = "rename"
    COPY = "copy"
    WRITE_TARGET = "write_target"
    APPEND_TRUNCATE = "append_truncate"
    EXTRACT = "extract"
    CREATE_ARCHIVE = "create_archive"
    BATCH = "batch"
    # 兼容老格式
    WRITE = "write"
    CREATE_FILE = "create_file"
    CREATE_FOLDER = "create_folder"


class UndoManager:
    """撤销管理器，管理撤销栈和批量操作上下文"""

    def __init__(self, max_undo: int = UndoConstants.MAX_UNDO):
        self._undo_stacks: Dict[str, List[Dict[str, Any]]] = {}
        self._active_session_id: str = "default"
        self._max_undo: int = max_undo
        self._undo_lock = threading.RLock()
        # 批量上下文: 不为 None 时,新写操作的 undo 记录会追加到此 list 而非主栈
        self._batch_context = threading.local()

    def set_active_session(self, session_id: str) -> None:
        """切换当前活动撤销栈所属会话"""
        with self._undo_lock:
            self._active_session_id = session_id or "default"

    def get_active_session(self) -> str:
        """返回当前活动会话 ID"""
        with self._undo_lock:
            return self._active_session_id

    def _active_stack(self) -> List[Dict[str, Any]]:
        """返回当前活动会话对应的撤销栈,缺失则创建"""
        with self._undo_lock:
            return self._undo_stacks.setdefault(self._active_session_id, [])

    def get_undo_stack(self) -> List[Dict[str, Any]]:
        """获取当前活动会话的撤销栈快照"""
        with self._undo_lock:
            return list(self._active_stack())

    def clear_undo_stack(self, session_id: Optional[str] = None) -> None:
        """清空指定(默认当前活动)会话的撤销栈,回收备份"""
        with self._undo_lock:
            sid = session_id or self._active_session_id
            stack = self._undo_stacks.pop(sid, [])
        # 锁外清理
        for action in stack:
            self._cleanup_action_backup(action)

    def clear_all_undo_stacks(self) -> None:
        """清空所有会话的撤销栈"""
        with self._undo_lock:
            all_stacks = list(self._undo_stacks.values())
            self._undo_stacks.clear()
        # 锁外清理
        for stack in all_stacks:
            for action in stack:
                self._cleanup_action_backup(action)

    def cleanup_old_backups(self, max_age_hours: int = UndoConstants.BACKUP_MAX_AGE_HOURS) -> int:
        """清理超过 max_age_hours 的临时备份目录"""
        tmpdir = Path(tempfile.gettempdir())
        cutoff = time.time() - max_age_hours * UndoConstants.SECONDS_PER_HOUR
        count = 0
        for p in tmpdir.glob("toolsagent_backup_*"):
            try:
                if p.is_dir() and p.stat().st_mtime < cutoff:
                    shutil.rmtree(p, ignore_errors=True)
                    count += 1
            except Exception:
                pass
        return count

    def _cleanup_action_backup(self, action: Dict[str, Any]) -> None:
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
                self._cleanup_snapshot(snap)
        # 批量类型: 递归清理 sub_actions
        if action.get("type") == UndoActionType.BATCH:
            for sub in action.get("sub_actions", []) or []:
                self._cleanup_action_backup(sub)

    def push_undo(self, action: Dict[str, Any]) -> None:
        """添加撤销操作。若处于批量上下文则追加到批量 sub_actions,否则进当前活动会话栈"""
        sub_actions = getattr(self._batch_context, "sub_actions", None)
        if sub_actions is not None:
            sub_actions.append(action)
            return
        pruned = []
        with self._undo_lock:
            stack = self._active_stack()
            stack.append(action)
            while len(stack) > self._max_undo:
                pruned.append(stack.pop(0))
        # 锁外执行文件系统清理，避免长时间持锁
        for old in pruned:
            self._cleanup_action_backup(old)

    def describe_action(self, action: Dict[str, Any]) -> str:
        """生成单条 undo 记录的人类可读描述"""
        t = action.get("type")
        if t == UndoActionType.DELETE:
            return f"删除 {action.get('path')}"
        if t == UndoActionType.MOVE:
            return f"移动 {action.get('src')} -> {action.get('dst')}"
        if t == UndoActionType.RENAME:
            return f"重命名 {action.get('src')} -> {action.get('dst')}"
        if t == UndoActionType.WRITE_TARGET:
            op = action.get("op") or "写入"
            return f"{op} {action.get('path')}"
        if t == UndoActionType.APPEND_TRUNCATE:
            return f"追加写入 {action.get('path')}"
        if t == UndoActionType.COPY:
            return f"复制 {action.get('src')} -> {action.get('dst')}"
        if t == UndoActionType.EXTRACT:
            return f"解压 {action.get('archive_path')} -> {action.get('output_path')}"
        if t == UndoActionType.CREATE_ARCHIVE:
            srcs = action.get('source_paths', [])
            if len(srcs) == 1:
                return f"压缩 {srcs[0]} -> {action.get('archive_path')}"
            else:
                return f"压缩 {len(srcs)} 个文件 -> {action.get('archive_path')}"
        if t == UndoActionType.BATCH:
            subs = action.get("sub_actions", [])
            label = action.get("label") or f"批量操作({len(subs)} 步)"
            return label
        # 兼容老格式
        if t == UndoActionType.WRITE:
            return f"覆盖写入 {action.get('path')}"
        if t == UndoActionType.CREATE_FILE:
            return f"创建文件 {action.get('path')}"
        if t == UndoActionType.CREATE_FOLDER:
            return f"创建文件夹 {action.get('path')}"
        return f"未知操作({t})"

    def get_undo_history(self, limit: int = 20) -> Dict[str, Any]:
        """返回当前活动会话撤销栈描述,最近的操作排在前面"""
        with self._undo_lock:
            snapshot = list(self._active_stack())
        items = []
        for idx, action in enumerate(reversed(snapshot[-limit:]), start=1):
            items.append({
                "index": idx,
                "type": action.get("type"),
                "description": self.describe_action(action),
            })
        return {"success": True, "count": len(snapshot), "items": items}

    def _backup_file(self, path: str) -> Optional[str]:
        """备份单个文件到临时目录，返回备份路径，超过最大大小则不备份"""
        path = Path(path)
        if not path.exists():
            return None

        # 计算文件/目录总大小
        total_size = 0
        if path.is_file():
            total_size = path.stat().st_size
        else:
            # 递归计算目录大小
            for f in path.rglob('*'):
                if f.is_file():
                    total_size += f.stat().st_size
                    # 超过限制立刻停止计算
                    if total_size > UndoConstants.MAX_BACKUP_SIZE:
                        break

        # 超过最大备份大小则不备份，避免磁盘耗尽
        if total_size > UndoConstants.MAX_BACKUP_SIZE:
            logger.warning(f"文件/目录 {path} 大小 {total_size/1024/1024:.2f}MB 超过最大备份限制 {UndoConstants.MAX_BACKUP_SIZE/1024/1024:.2f}MB，跳过备份")
            return None

        # 执行备份
        backup_dir = Path(tempfile.mkdtemp(prefix="toolsagent_backup_"))
        backup_path = backup_dir / path.name
        try:
            if path.is_file():
                # 备份文件时加共享读锁，确保备份过程中文件不被修改
                with open(path, 'rb') as f:
                    # 加共享读锁，阻塞式加锁
                    if HAS_FCNTL:
                        # Linux/Unix 平台
                        fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                    else:
                        # Windows 平台
                        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 0)

                    # 加锁成功后复制文件
                    shutil.copy2(path, backup_path)
            else:
                # 目录备份无法加全局锁，尽力而为
                shutil.copytree(path, backup_path)
        except Exception as e:
            logger.warning(f"备份 {path} 失败: {str(e)}")
            shutil.rmtree(backup_dir, ignore_errors=True)
            return None

        return str(backup_path)

    def capture_target_state(self, path: str) -> Dict[str, Any]:
        """捕获目标路径写入前的状态,用于事后构造可逆 undo

        返回 {"existed": bool, "is_dir": bool, "backup": str|None}
        若 existed=False, backup=None;否则 backup 指向临时备份
        """
        p = Path(path)
        if not p.exists():
            return {"existed": False, "is_dir": False, "backup": None}
        return {
            "existed": True,
            "is_dir": p.is_dir(),
            "backup": self._backup_file(path),
        }

    def _remove_target(self, path: str) -> None:
        """统一删除文件或文件夹(用于 undo 内部)"""
        p = Path(path)
        if not p.exists() and not p.is_symlink():
            return
        if p.is_file() or p.is_symlink():
            p.unlink()
        else:
            shutil.rmtree(p)

    def _restore_target(self, path: str, snapshot: Dict[str, Any]) -> None:
        """按 snapshot 把 path 还原回写操作前的状态"""
        if not snapshot:
            return
        self._remove_target(path)
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

    def _cleanup_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """释放 snapshot 占用的备份目录(undo 前用)"""
        if not snapshot:
            return
        bk = snapshot.get("backup")
        if bk:
            try:
                shutil.rmtree(Path(bk).parent, ignore_errors=True)
            except Exception:
                pass

    def _apply_undo_action(self, action: Dict[str, Any]) -> tuple[bool, Any]:
        """对单个 action 执行撤销;成功返回 (True, message),失败返回 (False, error)"""
        try:
            action_type = action["type"]
            if action_type == UndoActionType.DELETE:
                backup_path = action.get("backup")
                target_path = action["path"]
                if backup_path and Path(backup_path).exists():
                    shutil.move(backup_path, target_path)
                    self._cleanup_action_backup(action)
                    return True, f"已恢复: {target_path}"
                return False, f"备份缺失,无法恢复: {target_path}"
            if action_type == UndoActionType.MOVE:
                shutil.move(action["dst"], action["src"])
                dst_snap = action.get("dst_snap")
                if dst_snap and dst_snap.get("existed"):
                    self._restore_target(action["dst"], dst_snap)
                return True, f"已撤销移动: {action['dst']} -> {action['src']}"
            if action_type == UndoActionType.RENAME:
                Path(action["dst"]).rename(action["src"])
                dst_snap = action.get("dst_snap")
                if dst_snap and dst_snap.get("existed"):
                    self._restore_target(action["dst"], dst_snap)
                return True, f"已撤销重命名: {action['dst']} -> {action['src']}"
            if action_type == UndoActionType.COPY:
                dst_snap = action.get("dst_snap")
                if dst_snap is None:
                    self._remove_target(action["dst"])
                else:
                    self._restore_target(action["dst"], dst_snap)
                return True, f"已撤销复制到: {action['dst']}"
            if action_type == UndoActionType.EXTRACT:
                dst_snap = action.get("dst_snap")
                if dst_snap is None:
                    self._remove_target(action["output_path"])
                else:
                    self._restore_target(action["output_path"], dst_snap)
                return True, f"已撤销解压: {action['output_path']}"
            if action_type == UndoActionType.CREATE_ARCHIVE:
                dst_snap = action.get("dst_snap")
                if dst_snap is None:
                    self._remove_target(action["archive_path"])
                else:
                    self._restore_target(action["archive_path"], dst_snap)
                return True, f"已撤销压缩: {action['archive_path']}"
            if action_type == UndoActionType.WRITE_TARGET:
                self._restore_target(action["path"], action.get("snap"))
                label = action.get("op") or "写入"
                return True, f"已撤销{label}: {action['path']}"
            if action_type == UndoActionType.APPEND_TRUNCATE:
                target = Path(action["path"])
                if not action.get("existed"):
                    target.unlink(missing_ok=True)
                    return True, f"已撤销追加(删除新建文件): {action['path']}"
                with open(target, "rb+") as f:
                    f.truncate(int(action.get("prev_size", 0)))
                return True, f"已撤销追加: {action['path']}"
            if action_type == UndoActionType.BATCH:
                sub_actions = list(action.get("sub_actions", []))
                sub_results = []
                all_ok = True
                for sub in reversed(sub_actions):
                    ok, msg = self._apply_undo_action(sub)
                    sub_results.append({"success": ok, "message": msg})
                    if not ok:
                        all_ok = False
                label = action.get("label") or f"批量操作({len(sub_actions)} 步)"
                return all_ok, {
                    "label": label,
                    "sub_results": sub_results,
                }
            # 兼容老的 action 类型
            if action_type == UndoActionType.WRITE:
                backup_path = action.get("backup")
                target_path = action["path"]
                if backup_path and Path(backup_path).exists():
                    shutil.copy2(backup_path, target_path)
                    self._cleanup_action_backup(action)
                    return True, f"已恢复文件: {target_path}"
                return False, f"备份缺失,无法恢复: {target_path}"
            if action_type == UndoActionType.CREATE_FILE:
                Path(action["path"]).unlink(missing_ok=True)
                return True, f"已删除创建的文件: {action['path']}"
            if action_type == UndoActionType.CREATE_FOLDER:
                folder = Path(action["path"])
                if folder.exists():
                    shutil.rmtree(folder)
                return True, f"已删除创建的文件夹: {action['path']}"
            return False, f"未知的撤销操作类型: {action_type}"
        except Exception as e:
            logger.exception("撤销操作失败: %s", action)
            return False, f"撤销失败: {str(e)}"

    def undo_last(self, count: int = 1) -> Dict[str, Any]:
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
            with self._undo_lock:
                stack = self._active_stack()
                if not stack:
                    break
                action = stack.pop()
            ok, payload = self._apply_undo_action(action)
            if not ok:
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


# 全局单例实例
_global_undo_manager: Optional[UndoManager] = None
_undo_lock = threading.Lock()


def get_undo_manager() -> UndoManager:
    """获取全局撤销管理器单例"""
    global _global_undo_manager
    if _global_undo_manager is None:
        with _undo_lock:
            if _global_undo_manager is None:
                _global_undo_manager = UndoManager()
    return _global_undo_manager


# 兼容旧代码的全局函数
def set_active_session(session_id: str) -> None:
    """切换当前活动撤销栈所属会话"""
    get_undo_manager().set_active_session(session_id)


def get_active_session() -> str:
    """返回当前活动会话 ID"""
    return get_undo_manager().get_active_session()


def get_undo_stack() -> List[Dict[str, Any]]:
    """获取当前活动会话的撤销栈快照"""
    return get_undo_manager().get_undo_stack()


def clear_undo_stack(session_id: Optional[str] = None) -> None:
    """清空指定(默认当前活动)会话的撤销栈,回收备份"""
    get_undo_manager().clear_undo_stack(session_id)


def clear_all_undo_stacks() -> None:
    """清空所有会话的撤销栈(主要给测试用)"""
    get_undo_manager().clear_all_undo_stacks()


def cleanup_old_backups(max_age_hours: int = UndoConstants.BACKUP_MAX_AGE_HOURS) -> int:
    """清理超过 max_age_hours 的临时备份目录"""
    return get_undo_manager().cleanup_old_backups(max_age_hours)


def push_undo(action: Dict[str, Any]) -> None:
    """添加撤销操作。若处于批量上下文则追加到批量 sub_actions,否则进当前活动会话栈"""
    get_undo_manager().push_undo(action)


def get_undo_history(limit: int = 20) -> Dict[str, Any]:
    """返回当前活动会话撤销栈描述,最近的操作排在前面"""
    return get_undo_manager().get_undo_history(limit)


def undo_last(count: int = 1) -> Dict[str, Any]:
    """撤销最近 count 次操作（默认 1 次）。返回每一步的撤销结果"""
    return get_undo_manager().undo_last(count)


def capture_target_state(path: str) -> Dict[str, Any]:
    """捕获目标路径写入前的状态"""
    return get_undo_manager().capture_target_state(path)


def _remove_target(path: str) -> None:
    """统一删除文件或文件夹(用于 undo 内部)"""
    get_undo_manager()._remove_target(path)


def _restore_target(path: str, snapshot: Dict[str, Any]) -> None:
    """按 snapshot 把 path 还原回写操作前的状态"""
    get_undo_manager()._restore_target(path, snapshot)


def _cleanup_snapshot(snapshot: Dict[str, Any]) -> None:
    """释放 snapshot 占用的备份目录(undo 前用)"""
    get_undo_manager()._cleanup_snapshot(snapshot)


# 批量操作上下文
def _get_batch_context() -> Any:
    """获取当前批量上下文"""
    return getattr(get_undo_manager()._batch_context, "sub_actions", None)


def _set_batch_context(sub_actions: List[Dict[str, Any]]) -> None:
    """设置批量上下文"""
    get_undo_manager()._batch_context.sub_actions = sub_actions


def _clear_batch_context() -> None:
    """清除批量上下文"""
    get_undo_manager()._batch_context.sub_actions = None
