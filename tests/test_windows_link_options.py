"""Windows binaries get PE timestamps that do not depend on the link time."""

import pytest
from build_wheels import windows_link_options
from target_platform import OS


def test_windows_gets_brepro() -> None:
    assert windows_link_options(OS.WINDOWS, None) == "/Brepro"


def test_an_empty_caller_value_gets_brepro() -> None:
    assert windows_link_options(OS.WINDOWS, "  ") == "/Brepro"


def test_the_caller_options_are_kept() -> None:
    assert windows_link_options(OS.WINDOWS, "/DEBUG:NONE") == "/DEBUG:NONE /Brepro"


@pytest.mark.parametrize("present", ["/Brepro", "/BREPRO", "-brepro"])
def test_brepro_is_not_added_twice(present: str) -> None:
    value = f"/DEBUG:NONE {present}"
    assert windows_link_options(OS.WINDOWS, value) == value


def test_an_option_containing_brepro_is_not_mistaken_for_it() -> None:
    assert windows_link_options(OS.WINDOWS, "/Brepro:x") == "/Brepro:x /Brepro"


@pytest.mark.parametrize("os_name", [OS.DARWIN, OS.LINUX])
@pytest.mark.parametrize("value", [None, "/X"])
def test_other_platforms_are_unchanged(os_name: OS, value: str | None) -> None:
    assert windows_link_options(os_name, value) == value
