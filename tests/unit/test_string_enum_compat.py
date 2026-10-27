import json

from zcoder.core.enums import StringEnum
from zcoder.domain.models.product import AccountStatus


def test_string_enum_keeps_legacy_string_and_json_behavior():
    status = AccountStatus.ACTIVE

    assert isinstance(status, StringEnum)
    assert isinstance(status, str)
    assert status == "ACTIVE"
    assert str(status) == "AccountStatus.ACTIVE"
    assert json.dumps(status) == '"ACTIVE"'
