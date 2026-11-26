"""Renaming members of a wheel, RECORD included."""

import zipfile
from pathlib import Path

from module_wheel_init import module_init_name, rename_wheel_member


def _wheel(path: Path, name: str, members: dict[str, str]) -> Path:
    info = "pkg-1.0.dist-info"
    files = {
        **members,
        f"{info}/METADATA": f"Metadata-Version: 2.1\nName: {name}\nVersion: 1.0\n",
    }
    record = "".join(f"{n},sha256=h,{len(t)}\n" for n, t in files.items())
    files[f"{info}/RECORD"] = record + f"{info}/RECORD,,\n"
    with zipfile.ZipFile(path, "w") as zf:
        for member, text in files.items():
            zf.writestr(member, text)
    return path


def test_the_init_name_falls_back_to_the_distribution_name(tmp_path: Path) -> None:
    wheel = _wheel(tmp_path / "w.whl", "itk-RTK", {})
    assert module_init_name(wheel) == "itk/__init_rtk__.py"
    wheel = _wheel(tmp_path / "x.whl", "itk-foo-bar", {})
    assert module_init_name(wheel) == "itk/__init_foo__.py"


def test_the_init_name_comes_from_the_wrapped_module(tmp_path: Path) -> None:
    config = {"itk/Configuration/VkFFTBackendConfig.py": "depends = ()\n"}
    wheel = _wheel(tmp_path / "w.whl", "itk-vkfft", config)
    assert module_init_name(wheel) == "itk/__init_vkfftbackend__.py"


def test_a_rename_moves_the_member_and_its_record_line(tmp_path: Path) -> None:
    wheel = _wheel(tmp_path / "w.whl", "itk-a", {"itk/__init__.py": "x = 1\n"})
    assert rename_wheel_member(wheel, "itk/__init__.py", "itk/__init_a__.py")
    with zipfile.ZipFile(wheel) as zf:
        assert zf.read("itk/__init_a__.py") == b"x = 1\n"
        assert "itk/__init__.py" not in zf.namelist()
        record = zf.read("pkg-1.0.dist-info/RECORD").decode()
    assert "itk/__init_a__.py,sha256=h,6\n" in record
    assert "itk/__init__.py," not in record


def test_a_missing_member_leaves_the_wheel_alone(tmp_path: Path) -> None:
    wheel = _wheel(tmp_path / "w.whl", "itk-a", {})
    before = wheel.read_bytes()
    assert not rename_wheel_member(wheel, "itk/__init__.py", "itk/__init_a__.py")
    assert wheel.read_bytes() == before
