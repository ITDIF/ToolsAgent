import os
import sys
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Union, Optional, Callable, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from threading import Event, local

from ..security.sandbox import assert_safe_write_path, assert_safe_read_path, PathSafetyError
from ..infra.config import get_config
from ..infra.constants import ConfigDefaults, FileConstants
from ..infra.errors import ParameterError, error_response, ErrorCode
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
    undo_last as _undo_last,
    get_undo_history as _get_undo_history,
)

# 导入压缩工具函数，避免动态导入
from ..file.archive import extract_archive as _extract_archive, create_archive as _create_archive

logger = __import__("logging").getLogger(__name__)


def _require_safe_write(*path_args: str):
    """装饰器：为写操作函数自动添加路径安全校验。

    Args:
        *path_args: 需要校验的参数名列表（如 "path", "src", "dst"）。
                    如果在批量上下文中且路径已预先校验，则跳过。

    用法:
        @_require_safe_write("src", "dst")
        def move_file(src, dst): ...
    """
    def decorator(func):
        from functools import wraps
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 批量上下文中且路径已预校验，跳过
            if _get_batch_context() is not None and _is_paths_validated():
                return func(*args, **kwargs)
            # 解析参数：获取需要校验的路径值
            import inspect
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            cfg = get_config()
            for arg_name in path_args:
                path_value = bound.arguments.get(arg_name)
                if path_value is None:
                    continue
                try:
                    assert_safe_write_path(path_value, cfg)
                except PathSafetyError as e:
                    return {"success": False, "error": str(e)}
            return func(*args, **kwargs)
        return wrapper
    return decorator


class ToolNames:
    """工具名称常量"""
    MOVE_FILE = "move_file"
    COPY_FILE = "copy_file"
    DELETE_FILE = "delete_file"
    CREATE_FOLDER = "create_folder"
    CREATE_FILE = "create_file"
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    RENAME_FILE = "rename_file"
    SEARCH_FILES = "search_files"
    LIST_FILES = "list_files"
    SCAN_DISK = "scan_disk"
    EXTRACT_ARCHIVE = "extract_archive"
    CREATE_ARCHIVE = "create_archive"
    UNDO_LAST = "undo_last"
    UNDO_HISTORY = "undo_history"
    BATCH_OPERATIONS = "batch_operations"


@dataclass
class ScanProgress:
    """扫描进度信息"""
    current_path: str
    scanned_files: int
    scanned_dirs: int
    total_bytes: int
    elapsed_time: float


# 批量操作上下文：记录路径是否已预先校验
_batch_validation_context = local()


def _set_paths_validated(validated: bool) -> None:
    """设置当前批量操作的路径校验状态"""
    _batch_validation_context.paths_validated = validated


def _is_paths_validated() -> bool:
    """检查当前批量操作的路径是否已校验"""
    return getattr(_batch_validation_context, 'paths_validated', False)


# 允许在 batch_operations 内部调用的工具(写操作 + 只读读取)
_BATCH_ALLOWED_TOOLS = {
    ToolNames.MOVE_FILE, ToolNames.COPY_FILE, ToolNames.DELETE_FILE,
    ToolNames.CREATE_FOLDER, ToolNames.CREATE_FILE,
    ToolNames.WRITE_FILE, ToolNames.RENAME_FILE,
    ToolNames.READ_FILE, ToolNames.LIST_FILES, ToolNames.SEARCH_FILES,
    ToolNames.EXTRACT_ARCHIVE, ToolNames.CREATE_ARCHIVE,
}


@_require_safe_write("src", "dst")
def move_file(src: str, dst: str) -> Dict[str, Any]:
    """移动文件或文件夹"""
    src_path = Path(src)
    dst_path = Path(dst)

    if not src_path.exists():
        return {"success": False, "error": f"源路径不存在: {src}"}

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
        _cleanup_snapshot(dst_snap)
        return {"success": False, "error": f"权限不足，无法移动: {e}"}
    except OSError as e:
        # 处理各种操作系统错误（文件不存在、磁盘满等）
        _cleanup_snapshot(dst_snap)
        return {"success": False, "error": f"系统错误，无法移动: {e}"}
    except Exception as e:
        # 未预期的错误，记录堆栈信息
        logger.exception("移动文件时发生未预期错误: src=%s, dst=%s", src, dst)
        _cleanup_snapshot(dst_snap)
        return {"success": False, "error": f"未知错误: {e}"}


@_require_safe_write("dst")
def copy_file(src: str, dst: str) -> Dict[str, Any]:
    """复制文件或文件夹"""
    src_path = Path(src)
    dst_path = Path(dst)

    if not src_path.exists():
        return {"success": False, "error": f"源路径不存在: {src}"}

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
    except OSError as e:
        # 处理各种操作系统错误
        _restore_target(dst, dst_snap)
        return {"success": False, "error": f"系统错误，无法复制: {e}"}
    except Exception as e:
        # 未预期的错误，记录堆栈信息
        logger.exception("复制文件时发生未预期错误: src=%s, dst=%s", src, dst)
        _restore_target(dst, dst_snap)
        return {"success": False, "error": f"未知错误: {e}"}


@_require_safe_write("path")
def delete_file(path: str) -> Dict[str, Any]:
    """删除文件或文件夹"""
    file_path = Path(path)

    if not file_path.exists():
        return {"success": False, "error": f"路径不存在: {path}"}

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
    except OSError as e:
        # 处理各种操作系统错误
        return {"success": False, "error": f"系统错误，无法删除: {e}"}
    except Exception as e:
        # 未预期的错误，记录堆栈信息
        logger.exception("删除文件时发生未预期错误: path=%s", path)
        return {"success": False, "error": f"未知错误: {e}"}


@_require_safe_write("path")
def create_folder(path: str) -> Dict[str, Any]:
    """创建文件夹"""
    folder_path = Path(path)

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


@_require_safe_write("path")
def create_file(path: str, content: str = "") -> Dict[str, Any]:
    """创建文件,可指定内容。若目标已存在则备份原内容,撤销时可还原"""
    file_path = Path(path)

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
    try:
        assert_safe_read_path(path, cfg)
    except PathSafetyError as e:
        return {"success": False, "error": str(e)}

    max_bytes = int(cfg.get("max_read_bytes", ConfigDefaults.MAX_READ_BYTES))

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


@_require_safe_write("path")
def write_file(path: str, content: str, append: bool = False) -> Dict[str, Any]:
    """写入文件内容,支持覆盖或追加。两种模式都支持撤销"""
    file_path = Path(path)

    snap = None
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


@_require_safe_write("src", "dst")
def rename_file(src: str, dst: str) -> Dict[str, Any]:
    """重命名文件或文件夹"""
    src_path = Path(src)
    dst_path = Path(dst)

    if not src_path.exists():
        return {"success": False, "error": f"源路径不存在: {src}"}

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
    search_type: str = "all",
    progress_callback: Optional[Callable[[ScanProgress], None]] = None
) -> Dict[str, Any]:
    """搜索文件/文件夹，支持按名称匹配

    Args:
        pattern: 搜索关键词
        path: 搜索起始目录
        search_type: 搜索类型 (all/file/folder)
        progress_callback: 进度回调函数

    Returns:
        搜索结果字典
    """
    dir_path = Path(path)

    if not dir_path.exists():
        return {"success": False, "error": f"路径不存在: {path}"}

    cfg = get_config()
    try:
        assert_safe_read_path(path, cfg)
    except PathSafetyError as e:
        return {"success": False, "error": str(e)}

    max_results = int(cfg.get("max_search_results", ConfigDefaults.MAX_SEARCH_RESULTS))
    max_depth = int(cfg.get("max_search_depth", ConfigDefaults.MAX_SEARCH_DEPTH))
    tool_timeout = float(cfg.get("tool_timeout", ConfigDefaults.TOOL_TIMEOUT))
    base_depth = len(dir_path.resolve().parts)

    try:
        results = []
        truncated = False
        pattern_lower = pattern.lower()
        start_time = time.time()
        stop_event = Event()
        scanned_files = 0
        scanned_dirs = 0
        total_bytes = 0

        def _scan_directory(root: str, dirs: List[str], files: List[str]) -> None:
            """扫描单个目录（用于并发处理）"""
            nonlocal results, truncated, scanned_files, scanned_dirs, total_bytes

            if stop_event.is_set():
                return

            cur_depth = len(Path(root).resolve().parts) - base_depth
            if cur_depth >= max_depth:
                dirs.clear()  # 达到深度上限,不再继续向下
                return

            candidates = []
            if search_type in ("all", "folder"):
                candidates.extend((d, True) for d in dirs)
            if search_type in ("all", "file"):
                candidates.extend((f, False) for f in files)

            for name, is_dir in candidates:
                if stop_event.is_set() or truncated:
                    return

                if pattern_lower in name.lower():
                    results.append({
                        "name": name,
                        "type": "folder" if is_dir else "file",
                        "path": str(Path(root) / name)
                    })
                    if len(results) >= max_results:
                        truncated = True
                        stop_event.set()
                        return

            # 更新统计
            scanned_files += len(files)
            scanned_dirs += len(dirs)

            # 尝试计算当前目录大小（异步避免阻塞）
            if not stop_event.is_set():
                for f in files:
                    try:
                        file_path = Path(root) / f
                        if file_path.is_file():
                            total_bytes += file_path.stat().st_size
                    except (OSError, PermissionError):
                        pass

            # 调用进度回调
            if progress_callback and not stop_event.is_set():
                elapsed = time.time() - start_time
                progress_callback(ScanProgress(
                    current_path=root,
                    scanned_files=scanned_files,
                    scanned_dirs=scanned_dirs,
                    total_bytes=total_bytes,
                    elapsed_time=elapsed
                ))

        # 使用 os.walk 扫描，但分块处理以提高响应性
        for root, dirs, files in os.walk(dir_path):
            if time.time() - start_time > tool_timeout:
                truncated = True
                stop_event.set()
                break

            _scan_directory(root, dirs, files)

            if truncated or stop_event.is_set():
                break

        return {
            "success": True,
            "results": results,
            "path": path,
            "pattern": pattern,
            "truncated": truncated,
            "max_results": max_results,
            "scanned_files": scanned_files,
            "scanned_dirs": scanned_dirs,
            "elapsed_time": time.time() - start_time,
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

    cfg = get_config()
    try:
        assert_safe_read_path(path, cfg)
    except PathSafetyError as e:
        return {"success": False, "error": str(e)}

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
        if abs(size) < FileConstants.BYTES_PER_KB:
            return f"{size:.2f} {unit}"
        size /= FileConstants.BYTES_PER_KB
    return f"{size:.2f} PB"


def scan_disk(
    path: str = ".",
    max_depth: Optional[int] = None,
    max_results: Optional[int] = None,
    min_size: int = 0,
    progress_callback: Optional[Callable[[ScanProgress], None]] = None
) -> Dict[str, Any]:
    """扫描目录并统计各子文件夹大小,返回按大小降序排列的结果

    Args:
        path: 扫描起始目录
        max_depth: 最大递归深度
        max_results: 返回结果最大数量
        min_size: 最小字节数过滤
        progress_callback: 进度回调函数

    Returns:
        扫描结果字典
    """
    dir_path = Path(path)

    if not dir_path.exists():
        return {"success": False, "error": f"路径不存在: {path}"}

    cfg = get_config()
    try:
        assert_safe_read_path(path, cfg)
    except PathSafetyError as e:
        return {"success": False, "error": str(e)}

    max_depth = int(max_depth if max_depth is not None else cfg.get("max_search_depth", 10))
    max_results = int(max_results if max_results is not None else cfg.get("max_search_results", 100))
    tool_timeout = float(cfg.get("tool_timeout", ConfigDefaults.TOOL_TIMEOUT))
    max_workers = int(cfg.get("scan_max_workers", 4))  # 并发工作线程数

    base = str(dir_path.resolve())
    base_depth = len(dir_path.resolve().parts)
    sizes = {}
    truncated = False
    start_time = time.time()
    stop_event = Event()
    scanned_dirs = 0

    def _get_file_size(fp: str) -> int:
        """获取单个文件大小，忽略错误"""
        try:
            return os.path.getsize(fp)
        except (OSError, PermissionError):
            return 0

    def _process_dir(root: str, dirs: List[str], files: List[str]) -> int:
        """处理单个目录，返回该目录及其子目录的总大小"""
        nonlocal sizes, scanned_dirs

        cur_depth = len(Path(root).resolve().parts) - base_depth
        if cur_depth >= max_depth:
            dirs.clear()  # 达到深度上限,不再继续向下
            return 0

        # 并行计算文件大小
        root_size = 0
        file_paths = [os.path.join(root, f) for f in files]

        if len(file_paths) > 100:  # 文件多时使用并发
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(_get_file_size, fp) for fp in file_paths]
                for future in as_completed(futures):
                    if stop_event.is_set():
                        break
                    root_size += future.result()
        else:
            for fp in file_paths:
                if stop_event.is_set():
                    break
                root_size += _get_file_size(fp)

        sizes[root] = sizes.get(root, 0) + root_size

        # 将当前目录大小累加到所有祖先目录
        parent = root
        while True:
            parent = os.path.dirname(parent)
            if not parent or len(parent) < len(base):
                break
            sizes[parent] = sizes.get(parent, 0) + root_size

        scanned_dirs += 1

        # 调用进度回调
        if progress_callback and not stop_event.is_set():
            elapsed = time.time() - start_time
            total_bytes = sum(sizes.values())
            progress_callback(ScanProgress(
                current_path=root,
                scanned_files=len(files),
                scanned_dirs=scanned_dirs,
                total_bytes=total_bytes,
                elapsed_time=elapsed
            ))

        return root_size

    try:
        for root, dirs, files in os.walk(base):
            if time.time() - start_time > tool_timeout:
                truncated = True
                stop_event.set()
                break

            _process_dir(root, dirs, files)

            if stop_event.is_set():
                break

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
            "scanned_dirs": scanned_dirs,
            "elapsed_time": time.time() - start_time,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _extract_paths_from_operation(tool_name: str, tool_args: Dict[str, Any]) -> List[str]:
    """从工具参数中提取需要安全校验的路径列表

    Args:
        tool_name: 工具名称
        tool_args: 工具参数

    Returns:
        需要校验的路径列表
    """
    """从工具参数中提取需要安全校验的路径列表"""
    paths = []

    if tool_name == ToolNames.MOVE_FILE:
        paths.extend([tool_args.get("src", ""), tool_args.get("dst", "")])
    elif tool_name == ToolNames.COPY_FILE:
        paths.append(tool_args.get("dst", ""))
    elif tool_name == ToolNames.DELETE_FILE:
        paths.append(tool_args.get("path", ""))
    elif tool_name == ToolNames.CREATE_FOLDER:
        paths.append(tool_args.get("path", ""))
    elif tool_name == ToolNames.CREATE_FILE:
        paths.append(tool_args.get("path", ""))
    elif tool_name == ToolNames.WRITE_FILE:
        paths.append(tool_args.get("path", ""))
    elif tool_name == ToolNames.RENAME_FILE:
        paths.extend([tool_args.get("src", ""), tool_args.get("dst", "")])
    elif tool_name == ToolNames.EXTRACT_ARCHIVE:
        if tool_args.get("output_path"):
            paths.append(tool_args["output_path"])
        else:
            archive_path = tool_args.get("archive_path", "")
            if archive_path:
                paths.append(str(Path(archive_path).parent / Path(archive_path).stem))
    elif tool_name == ToolNames.CREATE_ARCHIVE:
        paths.append(tool_args.get("archive_path", ""))

    return [p for p in paths if p]  # 过滤空路径


def _validate_paths_batch(paths: List[str]) -> Dict[str, Any]:
    """批量校验路径安全性

    Returns:
        {"success": bool, "errors": {path: error_msg}}
    """
    if not paths:
        return {"success": True, "errors": {}}

    cfg = get_config()
    errors = {}
    seen = set()  # 去重，避免重复校验

    for path in paths:
        if path in seen:
            continue
        seen.add(path)

        try:
            assert_safe_write_path(path, cfg)
        except PathSafetyError as e:
            errors[path] = str(e)

    return {"success": len(errors) == 0, "errors": errors}


def batch_operations(
    operations: List[Dict[str, Any]],
    stop_on_error: bool = True,
    label: Optional[str] = None,
    interactive: bool = False,
    dry_run: bool = False,
    atomic: bool = True
) -> Dict[str, Any]:
    """批量执行多个文件操作,作为一个整体进入撤销栈。

    Args:
        operations: [{"tool": "...", "arguments": {...}}]
        stop_on_error: True 则首个失败就中断后续步骤;False 则尽力执行所有步骤
        label: 撤销历史中显示的标签
        interactive: 是否显示进度信息（用于交互式模式）
        dry_run: 是否为预览模式，只验证不执行实际操作
        atomic: 是否启用原子性，失败时自动回滚已执行的操作（默认True）

    Returns:
        每一步的结果,以及整体成功/失败标志。
        dry_run=True 时，返回 {"success": bool, "preview": [...], "dry_run": True}
    """
    if not isinstance(operations, list) or not operations:
        return {"success": False, "error": "operations 必须是非空数组"}

    # 嵌套调用直接拒绝,避免歧义
    if _get_batch_context() is not None:
        return {"success": False, "error": "不允许嵌套 batch_operations"}

    # 预先提取并批量校验所有路径
    all_paths = []
    for op in operations:
        if isinstance(op, dict):
            tool_name = op.get("tool")
            tool_args = op.get("arguments") or {}
            paths = _extract_paths_from_operation(tool_name, tool_args)
            all_paths.extend(paths)

    # 批量校验路径安全性
    if all_paths:
        validation = _validate_paths_batch(all_paths)
        if not validation["success"]:
            error_msg = f"路径安全校验失败: {len(validation['errors'])} 个路径不安全"
            return {
                "success": False,
                "error": error_msg,
                "invalid_paths": validation["errors"]
            }
        # 标记路径已校验，子操作可跳过重复校验
        _set_paths_validated(True)

    sub_actions: List[Dict[str, Any]] = []
    _set_batch_context(sub_actions)
    results = []
    failures = 0
    halted_index = None
    rollback_result = None

    try:
        total_ops = len(operations)

        # 如果是交互式模式且操作数量较多，显示进度
        if interactive and total_ops > 1:
            mode_msg = "预览" if dry_run else "执行"
            print(f"\033[90m  批量{mode_msg} {total_ops} 个操作...\033[0m", flush=True)

        for i, op in enumerate(operations):
            # 显示进度;single-op 时 progress 留空,但仍要保证变量已定义
            progress = f"[{i+1}/{total_ops}]" if (interactive and total_ops > 1) else ""

            if not isinstance(op, dict):
                error_msg = "operation 必须是对象"
                results.append({"index": i, "success": False, "error": error_msg, "tool": None, "dry_run": dry_run})
                failures += 1
                if interactive:
                    print(f"  {progress} ❌ {error_msg}")
                if stop_on_error:
                    halted_index = i
                    break
                continue

            tool_name = op.get("tool")
            tool_args = op.get("arguments") or {}
            if tool_name not in _BATCH_ALLOWED_TOOLS:
                error_msg = f"工具 {tool_name} 不允许在批量中调用"
                results.append({
                    "index": i, "tool": tool_name,
                    "success": False, "error": error_msg, "dry_run": dry_run
                })
                failures += 1
                if interactive:
                    print(f"  {progress} ❌ {error_msg}")
                if stop_on_error:
                    halted_index = i
                    break
                continue
            if not isinstance(tool_args, dict):
                error_msg = "arguments 必须是对象"
                results.append({
                    "index": i, "tool": tool_name,
                    "success": False, "error": error_msg, "dry_run": dry_run
                })
                failures += 1
                if interactive:
                    print(f"  {progress} ❌ {tool_name}: {error_msg}")
                if stop_on_error:
                    halted_index = i
                    break
                continue

            # 预览模式：只描述操作不执行
            if dry_run:
                preview_desc = f"将要执行: {tool_name}"
                if tool_args:
                    args_preview = {k: v for k, v in tool_args.items()
                                   if k not in ['content']}  # 排除长内容
                    if args_preview:
                        preview_desc += f" {args_preview}"

                step_result = {
                    "success": True,
                    "message": preview_desc,
                    "dry_run": True,
                    "preview": True
                }
                results.append({
                    "index": i,
                    "tool": tool_name,
                    "result": step_result,
                    "success": True,
                    "dry_run": True
                })

                if interactive:
                    print(f"  {progress} 🔍 {preview_desc}")
                continue

            # 正常执行模式
            try:
                # 先校验参数
                valid, error = validate_tool_parameters(tool_name, tool_args)
                if not valid:
                    step_result = {"success": False, "error": error["error"], "details": error}
                else:
                    step_result = TOOL_REGISTRY[tool_name](**tool_args)
            except TypeError as e:
                step_result = {"success": False, "error": f"参数错误: {e}"}
            except Exception as e:
                step_result = {"success": False, "error": str(e)}

            entry = {"index": i, "tool": tool_name, "result": step_result,
                     "success": bool(step_result.get("success")), "dry_run": False}
            results.append(entry)

            # 更新进度显示
            if interactive:
                if entry["success"]:
                    msg = step_result.get("message", "")
                    if len(msg) > 50:
                        msg = msg[:47] + "..."
                    print(f"  {progress} ✅ {msg}")
                else:
                    err = step_result.get("error", "未知错误")
                    if len(err) > 50:
                        err = err[:47] + "..."
                    print(f"  {progress} ❌ {err}")

            if not entry["success"]:
                failures += 1
                if stop_on_error:
                    halted_index = i
                    break
    finally:
        _clear_batch_context()
        _set_paths_validated(False)  # 重置校验状态

    # 原子性回滚：如果启用了原子性、stop_on_error且有失败，自动回滚所有已执行的操作
    rollback_success = True
    rollback_errors = []
    if atomic and stop_on_error and failures > 0 and not dry_run and sub_actions:
        if interactive:
            print(f"\033[93m  检测到执行失败，正在回滚 {len(sub_actions)} 个已执行的操作...\033[0m", flush=True)

        # 从undo模块获取管理器实例调用内部方法
        from ..security.undo import get_undo_manager
        undo_mgr = get_undo_manager()

        # 按相反顺序回滚（撤销操作需要反向执行）
        for action in reversed(sub_actions):
            try:
                ok, msg = undo_mgr._apply_undo_action(action)
                if not ok:
                    rollback_success = False
                    rollback_errors.append(f"回滚失败: {msg}")
                    if interactive:
                        print(f"    ❌ 回滚 {action.get('type', '未知操作')} 失败: {msg}")
                else:
                    if interactive:
                        print(f"    ✅ 已回滚 {action.get('type', '未知操作')}")
            except Exception as e:
                rollback_success = False
                rollback_errors.append(f"回滚异常: {str(e)}")
                if interactive:
                    print(f"    ❌ 回滚异常: {str(e)}")

        if interactive:
            if rollback_success:
                print(f"\033[92m  所有已执行操作已成功回滚，文件状态已恢复到批量操作前\033[0m", flush=True)
            else:
                print(f"\033[91m  部分操作回滚失败，文件状态可能不一致\033[0m", flush=True)

    # 显示最终结果
    if interactive and total_ops > 1:
        if dry_run:
            print(f"\033[90m  预览完成 ({len(results)} 个操作) - 使用 dry_run=False 实际执行\033[0m")
        elif failures == 0:
            print(f"\033[90m  全部完成 ({total_ops} 个操作) ✓\033[0m")
        else:
            if atomic and stop_on_error:
                if rollback_success:
                    print(f"\033[90m  批量操作失败，已自动回滚所有修改\033[0m")
                else:
                    print(f"\033[90m  批量操作失败，部分回滚失败，请手动检查文件状态\033[0m")
            else:
                print(f"\033[90m  完成 {total_ops - failures}/{total_ops} 个操作, {failures} 个失败\033[0m")

    # 预览模式直接返回，不入撤销栈
    if dry_run:
        return {
            "success": failures == 0,
            "dry_run": True,
            "preview": results,
            "total": len(operations),
            "failures": failures,
            "message": f"预览模式：共 {len(results)} 个操作，{failures} 个可能失败"
        }

    # 入撤销栈：如果已回滚则不入栈；否则（成功或部分成功未回滚）入栈
    if sub_actions and not (atomic and stop_on_error and failures > 0):
        push_undo({
            "type": UndoActionType.BATCH,
            "label": label or f"批量操作({len(sub_actions)} 步)",
            "sub_actions": sub_actions,
        })

    return {
        "success": failures == 0,
        "dry_run": False,
        "atomic": atomic,
        "rollback_success": rollback_success if (atomic and stop_on_error and failures > 0) else None,
        "rollback_errors": rollback_errors if (atomic and stop_on_error and failures > 0) else None,
        "total": len(operations),
        "executed": len(results),
        "failures": failures,
        "halted_at": halted_index,
        "results": results,
    }


# 导出旧的函数签名以保持兼容
def undo_last(count: int = 1) -> Dict[str, Any]:
    """撤销最近 count 次操作"""
    return _undo_last(count)

def get_undo_history(limit: int = 20) -> Dict[str, Any]:
    """获取撤销历史"""
    return _get_undo_history(limit)


# 工具注册表
TOOL_REGISTRY = {
    ToolNames.MOVE_FILE: move_file,
    ToolNames.COPY_FILE: copy_file,
    ToolNames.DELETE_FILE: delete_file,
    ToolNames.CREATE_FOLDER: create_folder,
    ToolNames.CREATE_FILE: create_file,
    ToolNames.READ_FILE: read_file,
    ToolNames.WRITE_FILE: write_file,
    ToolNames.RENAME_FILE: rename_file,
    ToolNames.SEARCH_FILES: search_files,
    ToolNames.LIST_FILES: list_files,
    ToolNames.SCAN_DISK: scan_disk,
    ToolNames.EXTRACT_ARCHIVE: _extract_archive,
    ToolNames.CREATE_ARCHIVE: _create_archive,
    ToolNames.UNDO_LAST: undo_last,
    ToolNames.UNDO_HISTORY: get_undo_history,
    ToolNames.BATCH_OPERATIONS: batch_operations,
}


TOOL_SCHEMAS = [
    {
        "name": ToolNames.UNDO_LAST,
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
        "name": ToolNames.UNDO_HISTORY,
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
        "name": ToolNames.BATCH_OPERATIONS,
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
                "label": {"type": "string", "description": "撤销历史显示的标签(可选)"},
                "dry_run": {
                    "type": "boolean",
                    "description": "是否为预览模式，只验证不执行实际操作(默认 false)"
                },
                "atomic": {
                    "type": "boolean",
                    "description": "是否启用原子性，失败时自动回滚已执行的操作(默认 true)"
                }
            },
            "required": ["operations"]
        }
    },
    {
        "name": ToolNames.MOVE_FILE,
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
        "name": ToolNames.COPY_FILE,
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
        "name": ToolNames.DELETE_FILE,
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
        "name": ToolNames.CREATE_FOLDER,
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
        "name": ToolNames.CREATE_FILE,
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
        "name": ToolNames.READ_FILE,
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
        "name": ToolNames.WRITE_FILE,
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
        "name": ToolNames.RENAME_FILE,
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
        "name": ToolNames.SEARCH_FILES,
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
        "name": ToolNames.LIST_FILES,
        "description": "列出指定目录下的文件和文件夹",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目录路径，默认为当前目录"}
            }
        }
    },
    {
        "name": ToolNames.SCAN_DISK,
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
        "name": ToolNames.EXTRACT_ARCHIVE,
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
        "name": ToolNames.CREATE_ARCHIVE,
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

# 工具Schema映射表，通过工具名快速查找Schema
TOOL_SCHEMA_MAP: Dict[str, Dict[str, Any]] = {schema["name"]: schema for schema in TOOL_SCHEMAS}


def validate_tool_parameters(tool_name: str, parameters: Dict[str, Any]) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    校验工具参数是否符合Schema定义
    Args:
        tool_name: 工具名称
        parameters: 工具参数
    Returns:
        (校验是否通过, 错误信息或None)
    """
    if tool_name not in TOOL_SCHEMA_MAP:
        return False, {
            "error": f"未知工具: {tool_name}",
            "code": ErrorCode.INVALID_PARAMETER.value
        }

    schema = TOOL_SCHEMA_MAP[tool_name]["input_schema"]
    required_fields = schema.get("required", [])
    properties = schema.get("properties", {})

    # 校验必填字段
    for field in required_fields:
        if field not in parameters:
            return False, {
                "error": f"缺少必填参数: {field}",
                "field": field,
                "code": ErrorCode.INVALID_PARAMETER.value
            }

    # 校验字段类型和约束
    for field, value in parameters.items():
        if field not in properties:
            continue  # 允许额外参数，不校验

        field_schema = properties[field]
        expected_type = field_schema.get("type")

        # 类型校验
        if expected_type:
            type_matched = False
            if expected_type == "string" and isinstance(value, str):
                type_matched = True
            elif expected_type == "integer" and isinstance(value, int):
                type_matched = True
            elif expected_type == "boolean" and isinstance(value, bool):
                type_matched = True
            elif expected_type == "array" and isinstance(value, list):
                type_matched = True
            elif expected_type == "object" and isinstance(value, dict):
                type_matched = True
            # 处理oneOf的情况
            elif "oneOf" in field_schema:
                for option in field_schema["oneOf"]:
                    option_type = option.get("type")
                    if option_type == "string" and isinstance(value, str):
                        type_matched = True
                        break
                    elif option_type == "array" and isinstance(value, list):
                        type_matched = True
                        break

            if not type_matched:
                return False, {
                    "error": f"参数 {field} 类型错误，期望 {expected_type}，实际 {type(value).__name__}",
                    "field": field,
                    "expected_type": expected_type,
                    "actual_type": type(value).__name__,
                    "code": ErrorCode.INVALID_PARAMETER.value
                }

        # 枚举值校验
        if "enum" in field_schema:
            allowed_values = field_schema["enum"]
            if value not in allowed_values:
                return False, {
                    "error": f"参数 {field} 值不合法，允许的值: {allowed_values}，实际: {value}",
                    "field": field,
                    "allowed_values": allowed_values,
                    "actual_value": value,
                    "code": ErrorCode.INVALID_PARAMETER.value
                }

        # 最小值校验
        if "minimum" in field_schema and isinstance(value, (int, float)):
            min_value = field_schema["minimum"]
            if value < min_value:
                return False, {
                    "error": f"参数 {field} 值不能小于 {min_value}，实际: {value}",
                    "field": field,
                    "minimum": min_value,
                    "actual_value": value,
                    "code": ErrorCode.INVALID_PARAMETER.value
                }

        # 最大值校验
        if "maximum" in field_schema and isinstance(value, (int, float)):
            max_value = field_schema["maximum"]
            if value > max_value:
                return False, {
                    "error": f"参数 {field} 值不能大于 {max_value}，实际: {value}",
                    "field": field,
                    "maximum": max_value,
                    "actual_value": value,
                    "code": ErrorCode.INVALID_PARAMETER.value
                }

    return True, None
