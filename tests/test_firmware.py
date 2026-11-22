from keyboardlight.firmware import version_tuple


def test_version_parsing_and_order():
    assert version_tuple('V3.14.29') == (3, 14, 29)
    assert version_tuple('30821') == (3, 8, 21)          # AULA file-name form ..._V30821.exe
    assert version_tuple('V3.14.29') > version_tuple('30821')
    assert version_tuple('garbage') == ()
