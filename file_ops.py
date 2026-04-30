
import os
import shutil
from pathlib import Path


def move_file(src, dst):
    """移动文件或文件夹"""
    src_path = Path(src)
    dst_path = Path(dst)

    if not src_path.exists():
        return {"success": False, "error": f"源路径不存在: {src}"}

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

    try:
        folder_path.mkdir(parents=True, exist_ok=True)
        return {"success": True, "message": f"已创建文件夹: {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_file(path, content=""):
    """创建文件，可指定内容"""
    file_path = Path(path)

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

    try:
        content = file_path.read_text(encoding="utf-8")
        return {"success": True, "path": path, "content": content}
    except Exception as e:
        return {"success": False, "error": str(e)}


def write_file(path, content, append=False):
    """写入文件内容，支持覆盖或追加"""
    file_path = Path(path)

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

    try:
        results = []
        # 遍历目录
        for item in dir_path.rglob("*"):
            # 根据类型过滤
            if search_type == "file" and not item.is_file():
                continue
            if search_type == "folder" and not item.is_dir():
                continue
            # 匹配模式
            if pattern.lower() in item.name.lower():
                results.append({
                    "name": item.name,
                    "type": "folder" if item.is_dir() else "file",
                    "path": str(item)
                })
        return {"success": True, "results": results, "path": path, "pattern": pattern}
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
    }
]

