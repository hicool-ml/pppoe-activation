"""
PPPoE激活请求校验模块
提供JSON Schema校验和ISP专属格式校验
"""
import json
import re
from pathlib import Path
from jsonschema import Draft7Validator, ValidationError

# 加载JSON Schema
SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "activate.schema.json"

with open(SCHEMA_PATH, encoding="utf-8") as f:
    ACTIVATE_SCHEMA = json.load(f)

validator = Draft7Validator(ACTIVATE_SCHEMA)


class SchemaInvalid(Exception):
    """JSON Schema校验失败异常"""
    def __init__(self, errors):
        self.errors = errors
        super().__init__("JSON schema validation failed")


class UsernameFormatError(Exception):
    """用户名格式错误异常"""
    pass


def validate_activate_payload(payload: dict):
    """
    校验激活请求的JSON Schema
    
    Args:
        payload: 请求数据字典
        
    Raises:
        SchemaInvalid: 当JSON Schema校验失败时
    """
    errors = sorted(validator.iter_errors(payload), key=lambda e: e.path)

    if errors:
        raise SchemaInvalid([
            {
                "path": ".".join(map(str, e.path)) if e.path else "root",
                "message": e.message
            }
            for e in errors
        ])


def validate_username_by_isp(isp: str, username: str):
    """
    根据ISP类型校验用户名格式
    
    Args:
        isp: ISP类型 (cdu, cmccgx, 96301, 10010, direct)
        username: 用户名
        
    Raises:
        UsernameFormatError: 当用户名格式不符合ISP要求时
    """
    if isp == "cmccgx":
        # 中国移动：11位手机号，1开头
        if not re.fullmatch(r"1\d{10}", username):
            raise UsernameFormatError("INVALID_CMCC_MOBILE")

    elif isp == "96301":
        # 中国电信：11位手机号，1开头
        if not re.fullmatch(r"1\d{10}", username):
            raise UsernameFormatError("INVALID_TELECOM_MOBILE")

    elif isp == "10010":
        # 中国联通：11位手机号，1开头
        if not re.fullmatch(r"1\d{10}", username):
            raise UsernameFormatError("INVALID_UNICOM_MOBILE")

    elif isp == "cdu":
        # 校园网：6-12位数字
        if not re.fullmatch(r"\d{6,12}", username):
            raise UsernameFormatError("INVALID_STUDENT_ID")

    # direct类型不做格式校验
