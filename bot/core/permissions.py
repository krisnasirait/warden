"""Mod-role decisions — pure, testable, no Discord imports."""

from __future__ import annotations


def has_mod_role(role_ids: list[int], mod_role: int | None, is_admin: bool = False) -> bool:
    if is_admin:
        return True
    if mod_role is None:
        return False
    return mod_role in role_ids
