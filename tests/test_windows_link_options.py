"""Windows binaries get PE timestamps that do not depend on the link time."""

import pytest
from build_wheels import windows_link_options


def test_windows_gets_brepro():
    assert windows_link_options("windows", None) == "/Brepro"


def test_an_empty_caller_value_gets_brepro():
    assert windows_link_options("windows", "  ") == "/Brepro"


def test_the_caller_options_are_kept():
    assert windows_link_options("windows", "/DEBUG:NONE") == "/DEBUG:NONE /Brepro"


@pytest.mark.parametrize("present", ["/Brepro", "/BREPRO", "-brepro"])
def test_brepro_is_not_added_twice(present):
    value = f"/DEBUG:NONE {present}"
    assert windows_link_options("windows", value) == value


def test_an_option_containing_brepro_is_not_mistaken_for_it():
    assert windows_link_options("windows", "/Brepro:x") == "/Brepro:x /Brepro"


@pytest.mark.parametrize("os_name", ["darwin", "linux"])
@pytest.mark.parametrize("value", [None, "/X"])
def test_other_platforms_are_unchanged(os_name, value):
    assert windows_link_options(os_name, value) == value
