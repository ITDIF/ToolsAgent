import os
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union
import zipfile
import tarfile

logger = logging.getLogger(__name__)

# 可选的 rarfile 库支持
try:
    import rarfile
    RARFILE_AVAILABLE = True
except ImportError:
    RARFILE_AVAILABLE = False

from ..security.sandbox import assert_safe_write_path, PathSafetyError
from ..infra.config import get_config
from ..security.undo import (
    UndoActionType,
    push_undo,
    capture_target_state,
    _cleanup_snapshot,
    _restore_target,
    _remove_target,
)


def _find_rar_executable() -> Optional[str]:
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


def extract_archive(archive_path: str, output_path: Optional[str] = None) -> Dict[str, Any]:
    """解压压缩文件（支持 zip, tar, tar.gz, tgz, tar.bz2, rar）

    Args:
        archive_path: 压缩文件路径
        output_path: 解压目标路径，默认解压到与压缩文件同名的文件夹

    Returns:
        {"success": bool, "message": str, "error": str}
    """
    archive_p = Path(archive_path)

    if not archive_p.exists():
        return {"success": False, "error": f"压缩文件不存在: {archive_path}"}

    if not archive_p.is_file():
        return {"success": False, "error": f"不是文件: {archive_path}"}

    # 确定输出路径
    if output_path is None:
        output_path = str(archive_p.parent / archive_p.stem)

    # 输出路径安全校验
    cfg = get_config()
    try:
        assert_safe_write_path(output_path, cfg)
    except PathSafetyError as e:
        return {"success": False, "error": str(e)}

    # 检查输出目录是否存在并备份
    dst_snap = capture_target_state(output_path)

    try:
        output_p = Path(output_path)
        output_p.mkdir(parents=True, exist_ok=True)

        ext = archive_p.suffix.lower()

        if ext == ".zip":
            with zipfile.ZipFile(archive_p, "r") as zf:
                zf.extractall(output_p)
        elif ext == ".rar":
            if not RARFILE_AVAILABLE:
                _cleanup_snapshot(dst_snap)
                return {"success": False, "error": "RAR 文件支持需要安装 rarfile 库: pip install rarfile"}
            try:
                with rarfile.RarFile(archive_p, "r") as rf:
                    rf.extractall(output_p)
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
        else:
            _cleanup_snapshot(dst_snap)
            supported = ".zip, .tar, .tar.gz, .tgz, .tar.bz2, .rar"
            return {"success": False, "error": f"不支持的压缩格式: {ext}。支持的格式: {supported}"}

        push_undo({
            "type": UndoActionType.EXTRACT,
            "archive_path": archive_path,
            "output_path": output_path,
            "dst_snap": dst_snap
        })
        return {"success": True, "message": f"已解压: {archive_path} -> {output_path}"}
    except PermissionError as e:
        _cleanup_snapshot(dst_snap)
        return {"success": False, "error": f"权限不足，无法解压: {e}"}
    except (tarfile.TarError, zipfile.BadZipFile) as e:
        _cleanup_snapshot(dst_snap)
        return {"success": False, "error": f"压缩文件损坏或格式错误: {e}"}
    except OSError as e:
        _restore_target(output_path, dst_snap)
        return {"success": False, "error": f"系统错误，无法解压: {e}"}
    except Exception as e:
        # 未预期的错误，记录堆栈信息
        logger.exception("解压文件时发生未预期错误: archive_path=%s", archive_path)
        _restore_target(output_path, dst_snap)
        return {"success": False, "error": f"未知错误: {e}"}


def create_archive(
    source_paths: Union[str, list[str]],
    archive_path: str,
    format: Optional[str] = None
) -> Dict[str, Any]:
    """创建压缩文件（支持 zip, tar, tar.gz, tgz, tar.bz2, rar）

    Args:
        source_paths: 要压缩的文件或文件夹路径（单个路径字符串或路径数组）
        archive_path: 输出压缩文件路径
        format: 压缩格式（zip, tar, gz, bz2, tgz, rar），默认根据文件后缀推断

    Returns:
        {"success": bool, "message": str, "error": str}
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
    cfg = get_config()
    try:
        assert_safe_write_path(archive_path, cfg)
    except PathSafetyError as e:
        return {"success": False, "error": str(e)}

    # 备份目标文件状态，用于撤销
    dst_snap = capture_target_state(archive_path)

    try:
        # 确保输出目录存在
        archive_p.parent.mkdir(parents=True, exist_ok=True)

        if ext in (".zip",):
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
        push_undo({
            "type": UndoActionType.CREATE_ARCHIVE,
            "source_paths": source_paths,
            "archive_path": archive_path,
            "dst_snap": dst_snap
        })

        return {"success": True, "message": f"已创建压缩文件: {archive_path}"}
    except PermissionError as e:
        _cleanup_snapshot(dst_snap)
        return {"success": False, "error": f"权限不足，无法创建压缩文件: {e}"}
    except (tarfile.TarError, zipfile.BadZipFile) as e:
        _cleanup_snapshot(dst_snap)
        return {"success": False, "error": f"压缩操作失败: {e}"}
    except OSError as e:
        _restore_target(archive_path, dst_snap)
        return {"success": False, "error": f"系统错误，无法创建压缩文件: {e}"}
    except Exception as e:
        # 未预期的错误，记录堆栈信息
        logger.exception("创建压缩文件时发生未预期错误: archive_path=%s", archive_path)
        _restore_target(archive_path, dst_snap)
        return {"success": False, "error": f"未知错误: {e}"}
