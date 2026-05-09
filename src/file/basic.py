import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Union, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from ..security.sandbox import assert_safe_write_path, PathSafetyError
from ..infra.config import get_config
from ..security.undo import (
    UndoActionType,
    push_undo,
    capture_target_state,
    _cleanup_snapshot,
    _restore_target,
    _remove_target,
    _get_batch_context,
    _set_batch_context,
    _clear_batch_context,
)
from ..infra.utils import log_action

logger = __import__("logging").getLogger(__name__)


# 允许在 batch_operations 内部调用的工具(写操作 + 只读读取)
_BATCH_ALLOWED_TOOLS = {
    "move_file", "copy_file", "delete_file",
    "create_folder", "create_file",
    "write_file", "rename_file",
    "read_file", "list_files", "search_files",
    "extract_archive", "create_archive",
}


def move_file(src: str, dst: str) -> Dict[str, Any]:
    """移动文件或文件夹"""
    src_path = Path(src)
    dst_path = Path(dst)

    if not src_path.exists():
        return {"success": False, "error": f"源路径不存在: {src}"}

    cfg = get_config()
    try:
        assert_safe_write_path(src, cfg)
        assert_safe_write_path(dst, cfg)
    except PathSafetyError as e:
        return {"success": False, "error": str(e)}

    dst_snap = capture_target_state(dst)
    try:
        shutil.move(str(src_path), str(dst_path))
        push_undo({
            "type": UndoActionType.MOVE,
            "src": src,
            "dst": dst,
            "dst_snap": dst_snap,
        })
        return {"success": True, "message": f"已移动: {src} -> {dst}"}
    except PermissionError as e:
        return {"success": False, "error": f"权限不足，无法移动: {e}"}
    except Exception as e:
        _cleanup_snapshot(dst_snap)
        return {"success": False, "error": str(e)}


def copy_file(src: str, dst: str) -> Dict[str, Any]:
    """复制文件或文件夹"""
    src_path = Path(src)
    dst_path = Path(dst)

    if not src_path.exists():
        return {"success": False, "error": f"源路径不存在: {src}"}

    cfg = get_config()
    try:
        assert_safe_write_path(dst, cfg)
    except PathSafetyError as e:
        return {"success": False, "error": str(e)}

    dst_snap = capture_target_state(dst)
    try:
        if dst_snap["existed"]:
            # shutil.copytree 不允许覆盖,先清空 dst 再复制
            _remove_target(dst)
        if src_path.is_file():
            shutil.copy2(str(src_path), str(dst_path))
        else:
            shutil.copytree(str(src_path), str(dst_path))
        push_undo({
            "type": UndoActionType.COPY,
            "src": src,
            "dst": dst,
            "dst_snap": dst_snap,
        })
        return {"success": True, "message": f"已复制: {src} -> {dst}"}
    except PermissionError as e:
        _restore_target(dst, dst_snap)
        return {"success": False, "error": f"权限不足，无法复制: {e}"}
    except Exception as e:
        # 失败时尽力还原
        _restore_target(dst, dst_snap)
        return {"success": False, "error": str(e)}


def delete_file(path: str) -> Dict[str, Any]:
    """删除文件或文件夹"""
    file_path = Path(path)

    if not file_path.exists():
        return {"success": False, "error": f"路径不存在: {path}"}

    cfg = get_config()
    try:
        assert_safe_write_path(path, cfg)
    except PathSafetyError as e:
        return {"success": False, "error": str(e)}

    try:
        # 备份被删除的文件/文件夹
        from ..security.undo import get_undo_manager
        backup_path = get_undo_manager()._backup_file(path)
        if file_path.is_file():
            file_path.unlink()
        else:
            shutil.rmtree(str(file_path))
        push_undo({
            "type": UndoActionType.DELETE,
            "path": path,
            "backup": backup_path
        })
        return {"success": True, "message": f"已删除: {path}"}
    except PermissionError as e:
        return {"success": False, "error": f"权限不足，无法删除: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_folder(path: str) -> Dict[str, Any]:
    """创建文件夹"""
    folder_path = Path(path)

    cfg = get_config()
    try:
        assert_safe_write_path(path, cfg)
    except PathSafetyError as e:
        return {"success": False, "error": str(e)}

    try:
        existed = folder_path.exists()
        folder_path.mkdir(parents=True, exist_ok=True)
        if not existed:
            push_undo({
                "type": UndoActionType.WRITE_TARGET,
                "path": path,
                "op": "创建文件夹",
                "snap": {"existed": False, "is_dir": False, "backup": None},
            })
        return {"success": True, "message": f"已创建文件夹: {path}"}
    except PermissionError as e:
        return {"success": False, "error": f"权限不足，无法创建文件夹: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_file(path: str, content: str = "") -> Dict[str, Any]:
    """创建文件,可指定内容。若目标已存在则备份原内容,撤销时可还原"""
    file_path = Path(path)

    cfg = get_config()
    try:
        assert_safe_write_path(path, cfg)
    except PathSafetyError as e:
        return {"success": False, "error": str(e)}

    snap = capture_target_state(path)
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        push_undo({
            "type": UndoActionType.WRITE_TARGET,
            "path": path,
            "op": "覆盖创建" if snap["existed"] else "创建文件",
            "snap": snap,
        })
        msg = "已覆盖创建" if snap["existed"] else "已创建文件"
        return {"success": True, "message": f"{msg}: {path}"}
    except PermissionError as e:
        _cleanup_snapshot(snap)
        return {"success": False, "error": f"权限不足，无法创建文件: {e}"}
    except Exception as e:
        _cleanup_snapshot(snap)
        return {"success": False, "error": str(e)}


def read_file(path: str) -> Dict[str, Any]:
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
    except PermissionError as e:
        return {"success": False, "error": f"权限不足，无法读取: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def write_file(path: str, content: str, append: bool = False) -> Dict[str, Any]:
    """写入文件内容,支持覆盖或追加。两种模式都支持撤销"""
    file_path = Path(path)

    cfg = get_config()
    try:
        assert_safe_write_path(path, cfg)
    except PathSafetyError as e:
        return {"success": False, "error": str(e)}

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if append:
            existed = file_path.exists()
            prev_size = file_path.stat().st_size if existed else 0
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(content)
            push_undo({
                "type": UndoActionType.APPEND_TRUNCATE,
                "path": path,
                "existed": existed,
                "prev_size": prev_size,
            })
            return {"success": True, "message": f"已追加文件: {path}"}
        snap = capture_target_state(path)
        try:
            file_path.write_text(content, encoding="utf-8")
        except Exception:
            _cleanup_snapshot(snap)
            raise
        push_undo({
            "type": UndoActionType.WRITE_TARGET,
            "path": path,
            "op": "覆盖写入" if snap["existed"] else "新建写入",
            "snap": snap,
        })
        return {"success": True, "message": f"已覆盖文件: {path}"}
    except PermissionError as e:
        _cleanup_snapshot(snap)
        return {"success": False, "error": f"权限不足，无法写入: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def rename_file(src: str, dst: str) -> Dict[str, Any]:
    """重命名文件或文件夹"""
    src_path = Path(src)
    dst_path = Path(dst)

    if not src_path.exists():
        return {"success": False, "error": f"源路径不存在: {src}"}

    cfg = get_config()
    try:
        assert_safe_write_path(src, cfg)
        assert_safe_write_path(dst, cfg)
    except PathSafetyError as e:
        return {"success": False, "error": str(e)}

    dst_snap = capture_target_state(dst)
    try:
        # POSIX 下 Path.rename 会原子覆盖目标,先备份后再 rename;
        # Windows 下若 dst 已存在会抛 FileExistsError,清掉 dst 之后再 rename
        if dst_snap["existed"]:
            _remove_target(dst)
        src_path.rename(dst_path)
        push_undo({
            "type": UndoActionType.RENAME,
            "src": src,
            "dst": dst,
            "dst_snap": dst_snap,
        })
        return {"success": True, "message": f"已重命名: {src} -> {dst}"}
    except PermissionError as e:
        _restore_target(dst, dst_snap)
        return {"success": False, "error": f"权限不足，无法重命名: {e}"}
    except Exception as e:
        # 失败时尝试还原 dst 原内容
        _restore_target(dst, dst_snap)
        return {"success": False, "error": str(e)}


def search_files(
    pattern: str,
    path: str = ".",
    search_type: str = "all"
) -> Dict[str, Any]:
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
    except PermissionError as e:
        logger.warning("搜索文件权限不足: %s", path)
        return {"success": False, "error": f"权限不足，无法搜索: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_files(path: str = ".") -> Dict[str, Any]:
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
    except PermissionError as e:
        return {"success": False, "error": f"权限不足，无法列出: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _human_size(size_bytes: int) -> str:
    """将字节数转为人类可读字符串"""
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    for unit in units:
        if abs(size) < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


def scan_disk(
    path: str = ".",
    max_depth: Optional[int] = None,
    max_results: Optional[int] = None,
    min_size: int = 0
) -> Dict[str, Any]:
    """扫描目录并统计各子文件夹大小,返回按大小降序排列的结果"""
    dir_path = Path(path)

    if not dir_path.exists():
        return {"success": False, "error": f"路径不存在: {path}"}

    cfg = get_config()
    max_depth = int(max_depth if max_depth is not None else cfg.get("max_search_depth", 10))
    max_results = int(max_results if max_results is not None else cfg.get("max_search_results", 100))
    tool_timeout = float(cfg.get("tool_timeout", 30))

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
                except PermissionError:
                    pass
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


def batch_operations(
    operations: List[Dict[str, Any]],
    stop_on_error: bool = True,
    label: Optional[str] = None
) -> Dict[str, Any]:
    """批量执行多个文件操作,作为一个整体进入撤销栈。

    Args:
        operations: [{"tool": "...", "arguments": {...}}]
        stop_on_error: True 则首个失败就中断后续步骤;False 则尽力执行所有步骤
        label: 撤销历史中显示的标签

    Returns:
        每一步的结果,以及整体成功/失败标志
    """
    if not isinstance(operations, list) or not operations:
        return {"success": False, "error": "operations 必须是非空数组"}

    # 嵌套调用直接拒绝,避免歧义
    if _get_batch_context() is not None:
        return {"success": False, "error": "不允许嵌套 batch_operations"}

    sub_actions: List[Dict[str, Any]] = []
    _set_batch_context(sub_actions)
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
        _clear_batch_context()

    # 仅当至少有一步成功且产生了 sub_action 时才入栈
    if sub_actions:
        push_undo({
            "type": UndoActionType.BATCH,
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


# 导出旧的函数签名以保持兼容
undo_last = lambda count=1: __import__("src.security.undo", fromlist=["undo_last"]).undo_last(count)
get_undo_history = lambda limit=20: __import__("src.security.undo", fromlist=["get_undo_history"]).get_undo_history(limit)


# 工具注册表
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
    "extract_archive": lambda **kw: __import__("src.file.archive", fromlist=["extract_archive"]).extract_archive(**kw),
    "create_archive": lambda **kw: __import__("src.file.archive", fromlist=["create_archive"]).create_archive(**kw),
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

