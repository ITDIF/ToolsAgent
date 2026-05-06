
import os
import shutil
from pathlib import Path

from path_safety import assert_safe_write_path, PathSafetyError
from config import get_config


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

    try:
        shutil.move(str(src_path), str(dst_path))
        return {"success": True, "message": f"已移动: {src} -> {dst}"}
    except Exception as e:
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

    try:
        if src_path.is_file():
            shutil.copy2(str(src_path), str(dst_path))
        else:
            shutil.copytree(str(src_path), str(dst_path))
        return {"success": True, "message": f"已复制: {src} -> {dst}"}
    except Exception as e:
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
        if file_path.is_file():
            file_path.unlink()
        else:
            shutil.rmtree(str(file_path))
        return {"success": True, "message": f"已删除: {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_folder(path):
    """创建文件夹"""
    folder_path = Path(path)

    err = _safety_check(path)
    if err:
        return err

    try:
        folder_path.mkdir(parents=True, exist_ok=True)
        return {"success": True, "message": f"已创建文件夹: {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_file(path, content=""):
    """创建文件，可指定内容"""
    file_path = Path(path)

    err = _safety_check(path)
    if err:
        return err

    try:
        # 确保父目录存在
        file_path.parent.mkdir(parents=True, exist_ok=True)
        # 写入文件
        file_path.write_text(content, encoding="utf-8")
        return {"success": True, "message": f"已创建文件: {path}"}
    except Exception as e:
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
    """写入文件内容，支持覆盖或追加"""
    file_path = Path(path)

    err = _safety_check(path)
    if err:
        return err

    try:
        # 确保父目录存在
        file_path.parent.mkdir(parents=True, exist_ok=True)
        # 写入文件
        if append:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(content)
        else:
            file_path.write_text(content, encoding="utf-8")
        mode = "追加" if append else "覆盖"
        return {"success": True, "message": f"已{mode}文件: {path}"}
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

    try:
        src_path.rename(dst_path)
        return {"success": True, "message": f"已重命名: {src} -> {dst}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def search_files(path, pattern, search_type="all"):
    """搜索文件/文件夹，支持按名称匹配"""
    dir_path = Path(path)

    if not dir_path.exists():
        return {"success": False, "error": f"路径不存在: {path}"}

    cfg = get_config()
    max_results = int(cfg.get("max_search_results", 100))
    max_depth = int(cfg.get("max_search_depth", 10))
    base_depth = len(dir_path.resolve().parts)

    try:
        results = []
        truncated = False
        pattern_lower = pattern.lower()

        for root, dirs, files in os.walk(dir_path):
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
    min_size = int(min_size)

    base = str(dir_path.resolve())
    base_depth = len(dir_path.resolve().parts)
    sizes = {}

    try:
        for root, dirs, files in os.walk(base):
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

        truncated = len(items) > max_results
        if truncated:
            items = items[:max_results]

        return {
            "success": True,
            "path": path,
            "items": items,
            "truncated": truncated,
            "count": len(items),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


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
}


TOOL_SCHEMAS = [
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
    }
]

