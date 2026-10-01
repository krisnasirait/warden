from bot.core.permissions import has_mod_role

MOD_ROLE = 42
OTHER_ROLE = 7


def test_admin_always_passes():
    assert has_mod_role([], None, is_admin=True)


def test_mod_role_present():
    assert has_mod_role([OTHER_ROLE, MOD_ROLE], MOD_ROLE)


def test_wrong_roles_fail():
    assert not has_mod_role([OTHER_ROLE], MOD_ROLE)


def test_unconfigured_mod_role_fails():
    assert not has_mod_role([OTHER_ROLE], None)


def test_no_roles_fail():
    assert not has_mod_role([], MOD_ROLE)
