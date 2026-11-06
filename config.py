import os
import re as _re
import sys
import json
import socket
import uuid
from pathlib import Path

CONFIG_FILENAME = "config.json"
DEVICE_ID_FILENAME = ".shipment_tool_device_id"

DEFAULT_RETENTION_DAYS = 15
DEFAULT_AUTO_EXPORT_BOXES = 0
DEFAULT_AUTO_CHECK_PREV_DAYS = 1
DEFAULT_SPECIAL_MODE = 1
DEFAULT_IGNORE_BOX_FORMAT = 1
DEFAULT_IGNORE_SN_FORMAT = 1
DEFAULT_CHECK_DUPLICATES = 0
DEFAULT_UNIFY_VERSION_WHEN_IGNORE_BOX = 1
DEFAULT_SUMMARY_FORMAT_IS_CSV = 1
DEFAULT_SOURCE_DIR = "\\\\10.10.86.11\\M2177\\07.整轴出货数据"
DEFAULT_SOURCE_SUBDIRS = ["Hinge-4346", "Hinge-4471", "Hinge-4472"]  # 设备子文件夹名列表；空列表表示直接扫描 source_dir（向后兼容）
DEFAULT_FORCE_MERGE_ON_GAP = 1
DEFAULT_BACKUP_DIR = "\\\\10.10.86.11\\M2177\\03.QE\\Merged_Log_Database"


def _get_default_log_dir() -> Path:
    env_dir = os.environ.get('MERGE_LOG_DIR')
    if env_dir:
        return Path(env_dir)
    if getattr(sys, 'frozen', False):
        base_dir = Path(sys.executable).parent
    else:
        base_dir = Path(__file__).parent
    return base_dir / 'merge_log'


def _find_config_file() -> Path | None:
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
    else:
        exe_dir = Path(__file__).parent
    config_path = exe_dir / CONFIG_FILENAME
    if config_path.exists():
        return config_path
    home_config = Path.home() / CONFIG_FILENAME
    if home_config.exists():
        return home_config
    return None


def _load_config() -> dict:
    config_path = _find_config_file()
    if not config_path:
        return {}
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _normalize_unc_path(path_str: str) -> str:
    """规范化 Windows UNC 网络路径。
    - Windows: 把单个前导反斜杠补成双反斜杠；
    - macOS/Linux: 路径不以 '\\' 开头时不受影响（如 /Volumes/...）。
    """
    path_str = path_str.strip()
    if path_str.startswith('\\\\'):
        return path_str
    if path_str.startswith('\\') and not path_str.startswith('\\\\'):
        return '\\' + path_str
    return path_str


def _load_config_log_dir() -> Path | None:
    config = _load_config()
    log_dir_str = config.get('log_dir')
    if log_dir_str:
        normalized = _normalize_unc_path(log_dir_str)
        return Path(normalized)
    return None


def _load_config_retention_days() -> int:
    config = _load_config()
    retention = config.get('retention_days', DEFAULT_RETENTION_DAYS)
    try:
        days = int(retention)
        if days > 0:
            return days
    except (ValueError, TypeError):
        pass
    return DEFAULT_RETENTION_DAYS


def _load_config_bool_setting(key: str, default: int) -> bool:
    config = _load_config()
    val = config.get(key, default)
    return str(val) == '1'


# ====== 设备唯一识别码 ======

def _generate_device_id() -> str:
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "UNKNOWN"
    try:
        mac_int = uuid.getnode()
        mac_hex = f"{mac_int:012x}".upper()
    except Exception:
        mac_hex = uuid.uuid4().hex[:12].upper()
    return f"{hostname}_{mac_hex}"


def _get_or_create_device_id() -> str:
    device_id_file = Path.home() / DEVICE_ID_FILENAME
    try:
        if device_id_file.exists():
            with open(device_id_file, 'r', encoding='utf-8') as f:
                did = f.read().strip()
            if did:
                return did
    except Exception:
        pass

    did = _generate_device_id()
    try:
        with open(device_id_file, 'w', encoding='utf-8') as f:
            f.write(did)
    except Exception:
        pass
    return did


DEVICE_ID = _get_or_create_device_id()


def get_device_id() -> str:
    return DEVICE_ID


# ====== backup_dir / force_merge_on_gap / 子文件夹 ======

def get_backup_dir() -> str:
    config = _load_config()
    val = config.get('backup_dir', DEFAULT_BACKUP_DIR)
    if isinstance(val, str):
        return _normalize_unc_path(val)
    return ''


def get_force_merge_on_gap() -> bool:
    return _load_config_bool_setting('force_merge_on_gap', DEFAULT_FORCE_MERGE_ON_GAP)


def get_unify_version_when_ignore_box() -> bool:
    return _load_config_bool_setting(
        'unify_version_when_ignore_box', DEFAULT_UNIFY_VERSION_WHEN_IGNORE_BOX
    )


def get_summary_format_is_csv() -> bool:
    return _load_config_bool_setting(
        'summary_format_is_csv', DEFAULT_SUMMARY_FORMAT_IS_CSV
    )


def get_source_dir() -> str:
    """读取 source_dir（07.出货数据 根目录）。"""
    config = _load_config()
    val = config.get('source_dir', DEFAULT_SOURCE_DIR)
    if isinstance(val, str):
        return _normalize_unc_path(val)
    return ''


def _parse_subdirs_value(val) -> list[str]:
    """兼容 list[str] / 逗号或分号分隔字符串，返回清洗后的子文件夹名列表。"""
    result = []
    if isinstance(val, (list, tuple)):
        for v in val:
            s = str(v).strip()
            if s:
                result.append(s)
    elif isinstance(val, str):
        parts = _re.split(r'[,，;；]+', val)
        for p in parts:
            s = p.strip()
            if s:
                result.append(s)
    return result


def get_source_subdirs() -> list[str]:
    """读取设备子文件夹名列表。
    返回空列表表示直接扫描 source_dir（向后兼容旧行为）。"""
    config = _load_config()
    val = config.get('source_subdirs', DEFAULT_SOURCE_SUBDIRS)
    return _parse_subdirs_value(val)


def _write_config_field(key: str, value) -> bool:
    config_path = _find_config_file()
    if config_path is None:
        try:
            _ensure_config_file(_get_default_log_dir())
        except Exception:
            pass
        config_path = _find_config_file()
        if config_path is None:
            return False

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
    except Exception:
        config_data = {}

    config_data[key] = value

    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)
        return True
    except Exception:
        return False


def set_source_dir(path_str: str) -> bool:
    path_str = (path_str or '').strip()
    return _write_config_field('source_dir', path_str)


def set_source_subdirs(subdirs) -> bool:
    """保存设备子文件夹列表。参数可为 list[str] 或逗号/分号分隔的字符串。"""
    cleaned = _parse_subdirs_value(subdirs)
    return _write_config_field('source_subdirs', cleaned)


# 配置文件字段顺序（与"设置"面板一致）
_CONFIG_ORDER = [
    'log_dir',
    'retention_days',
    'auto_export_boxes',
    'auto_check_prev_days',
    'special_mode_default',
    'ignore_box_format',
    'unify_version_when_ignore_box',
    'ignore_sn_format',
    'check_duplicates',
    'summary_format_is_csv',
    'source_dir',
    'source_subdirs',
    'force_merge_on_gap',
    'backup_dir',
]

_CONFIG_DEFAULTS = {
    'log_dir': None,
    'retention_days': DEFAULT_RETENTION_DAYS,
    'auto_export_boxes': DEFAULT_AUTO_EXPORT_BOXES,
    'auto_check_prev_days': DEFAULT_AUTO_CHECK_PREV_DAYS,
    'special_mode_default': DEFAULT_SPECIAL_MODE,
    'ignore_box_format': DEFAULT_IGNORE_BOX_FORMAT,
    'unify_version_when_ignore_box': DEFAULT_UNIFY_VERSION_WHEN_IGNORE_BOX,
    'ignore_sn_format': DEFAULT_IGNORE_SN_FORMAT,
    'check_duplicates': DEFAULT_CHECK_DUPLICATES,
    'summary_format_is_csv': DEFAULT_SUMMARY_FORMAT_IS_CSV,
    'source_dir': DEFAULT_SOURCE_DIR,
    'source_subdirs': list(DEFAULT_SOURCE_SUBDIRS),
    'force_merge_on_gap': DEFAULT_FORCE_MERGE_ON_GAP,
    'backup_dir': DEFAULT_BACKUP_DIR,
}


def _ensure_config_file(default_log_dir: Path):
    defaults = dict(_CONFIG_DEFAULTS)
    defaults['log_dir'] = str(default_log_dir)
    defaults['source_subdirs'] = list(_CONFIG_DEFAULTS['source_subdirs'])

    config_path = _find_config_file()
    if config_path is None:
        if getattr(sys, 'frozen', False):
            config_dir = Path(sys.executable).parent
        else:
            config_dir = Path(__file__).parent
        config_path = config_dir / CONFIG_FILENAME
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(defaults, f, indent=4, ensure_ascii=False)
        except Exception:
            home_config = Path.home() / CONFIG_FILENAME
            try:
                with open(home_config, 'w', encoding='utf-8') as f:
                    json.dump(defaults, f, indent=4, ensure_ascii=False)
            except Exception:
                pass
    else:
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            changed = False
            new_config = {}
            for k in _CONFIG_ORDER:
                if k in config_data:
                    new_config[k] = config_data[k]
                else:
                    new_config[k] = defaults[k]
                    changed = True
            for k, v in config_data.items():
                if k not in new_config:
                    new_config[k] = v
                    changed = True

            if changed:
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(new_config, f, indent=4, ensure_ascii=False)
        except Exception:
            pass


def _get_log_dir() -> Path:
    env_dir = os.environ.get('MERGE_LOG_DIR')
    if env_dir:
        candidate = Path(env_dir)
    else:
        config_dir = _load_config_log_dir()
        if config_dir:
            candidate = config_dir
        else:
            return _get_default_log_dir()

    try:
        if candidate.exists() and candidate.is_file():
            candidate = candidate.parent
    except Exception:
        pass

    return candidate


LOG_DIR = _get_log_dir()
DB_PATH = LOG_DIR / 'merge_log.db'
RETENTION_DAYS = _load_config_retention_days()
AUTO_EXPORT_BOXES = _load_config_bool_setting('auto_export_boxes', DEFAULT_AUTO_EXPORT_BOXES)
AUTO_CHECK_PREV_DAYS = _load_config_bool_setting('auto_check_prev_days', DEFAULT_AUTO_CHECK_PREV_DAYS)
SPECIAL_MODE_DEFAULT = _load_config_bool_setting('special_mode_default', DEFAULT_SPECIAL_MODE)
IGNORE_BOX_FORMAT_DEFAULT = _load_config_bool_setting('ignore_box_format', DEFAULT_IGNORE_BOX_FORMAT)
IGNORE_SN_FORMAT_DEFAULT = _load_config_bool_setting('ignore_sn_format', DEFAULT_IGNORE_SN_FORMAT)
CHECK_DUPLICATES_DEFAULT = _load_config_bool_setting('check_duplicates', DEFAULT_CHECK_DUPLICATES)
UNIFY_VERSION_WHEN_IGNORE_BOX = _load_config_bool_setting(
    'unify_version_when_ignore_box', DEFAULT_UNIFY_VERSION_WHEN_IGNORE_BOX
)
SUMMARY_FORMAT_IS_CSV = _load_config_bool_setting(
    'summary_format_is_csv', DEFAULT_SUMMARY_FORMAT_IS_CSV
)
SOURCE_DIR = get_source_dir()
SOURCE_SUBDIRS = get_source_subdirs()
XLSX_SUFFIX = '.xlsx'
CSV_SUFFIX = '.csv'


def ensure_log_dir() -> Path:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise RuntimeError(
            f"无法创建日志目录 {LOG_DIR}，请检查：\n"
            f"1. 路径是否正确（网络共享盘是否已连接？）\n"
            f"2. 是否有写入权限\n"
            f"3. 可修改配置文件 config.json 中的 log_dir 项，或设置环境变量 MERGE_LOG_DIR\n"
            f"原始错误：{e}"
        )
    _ensure_config_file(LOG_DIR)
    return LOG_DIR