# Copyright (C) 2026 Berk Kivircik. SPDX-License-Identifier: GPL-3.0-only
"""Verify Windows menu branding and main toolbar in profiles isolated from the user."""
import argparse
import ctypes as c
from ctypes import wintypes as wt
from pathlib import Path
import hashlib
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "updater"))
from windows_driver import Callback, bind, close, k, menus, u, wait_window


CUSTOMIZE = 49951
ABOUT, HOME, NEW, OPEN = 47000, 47001, 41001, 41002
LIST, UP, RESET = 61092, 61094, 61096
SET_ITEM_STATE = 0x102B
TB_COMMANDTOINDEX, TB_ISBUTTONHIDDEN, TB_GETITEMRECT = 0x419, 0x40C, 0x41D
CONFIG = "notequ-main-toolbar.cfg"

bind(u, "EnumWindows", wt.BOOL, [Callback, wt.LPARAM])
bind(u, "GetWindowTextW", c.c_int, [wt.HWND, wt.LPWSTR, c.c_int])
bind(u, "GetDlgItem", wt.HWND, [wt.HWND, c.c_int])
bind(u, "IsWindowVisible", wt.BOOL, [wt.HWND])
bind(u, "GetClientRect", wt.BOOL, [wt.HWND, c.POINTER(wt.RECT)])
bind(u, "GetWindow", wt.HWND, [wt.HWND, wt.UINT])
bind(u, "GetMenuState", wt.UINT, [wt.HMENU, wt.UINT, wt.UINT])


def wait_until(check, label):
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if value := check():
            return value
        time.sleep(0.1)
    raise AssertionError(label)


def same_process(hwnd, process):
    pid = wt.DWORD()
    u.GetWindowThreadProcessId(hwnd, c.byref(pid))
    return pid.value == process.pid


def command_label(hwnd, command):
    buffer = c.create_unicode_buffer(512)
    u.GetMenuStringW(u.GetMenu(hwnd), command, buffer, len(buffer), 0)
    return buffer.value.replace("&", "").split("\t")[0]


def find_child(hwnd, cls, test=lambda _: True):
    found = []

    @Callback
    def visit(child, _):
        name = c.create_unicode_buffer(100)
        u.GetClassNameW(child, name, 100)
        if name.value == cls and test(child):
            found.append(child)
        return True

    u.EnumChildWindows(hwnd, visit, 0)
    return found[0] if found else None


def toolbar(hwnd):
    return find_child(hwnd, "ToolbarWindow32", lambda child: u.SendMessageW(child, TB_COMMANDTOINDEX, CUSTOMIZE, 0) >= 0)


def formatting_toolbar(hwnd):
    return find_child(hwnd, "NoteQuFormattingToolbar", lambda child: bool(u.GetDlgItem(child, 16)))


def find_dialog(process, hwnd):
    found = []

    @Callback
    def visit(window, _):
        if (same_process(window, process) and u.GetWindow(window, 4) == hwnd and
                u.IsWindowVisible(window) and u.GetDlgItem(window, LIST)):
            found.append(window)
        return True

    u.EnumWindows(visit, 0)
    return found[0] if found else None


def launch(exe):
    process = subprocess.Popen([str(exe), "-multiInst"], cwd=exe.parent)
    try:
        pid, hwnd = wait_window(exe)
        assert pid == process.pid
        return process, hwnd
    except BaseException:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        raise


def finish(exe, process):
    if process.poll() is None:
        try:
            _, hwnd = wait_window(exe, timeout=3)
            dialog = find_dialog(process, hwnd)
            if dialog:
                close_dialog(process, hwnd, dialog, 2)
            close(exe)
            assert process.wait(timeout=20) == 0
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)


def label_for_dialog(dialog):
    text = c.create_unicode_buffer(256)
    u.GetWindowTextW(dialog, text, len(text))
    return text.value


def send_remote(pid, hwnd, message, parameter, data):
    handle = k.OpenProcess(0x38, False, pid)
    assert handle
    remote = k.VirtualAllocEx(handle, None, len(data), 0x3000, 4)
    try:
        assert remote and k.WriteProcessMemory(handle, remote, data, len(data), None)
        result = u.SendMessageW(hwnd, message, parameter, remote)
        buffer = c.create_string_buffer(len(data))
        assert k.ReadProcessMemory(handle, remote, buffer, len(buffer), None)
        return result, buffer.raw
    finally:
        if remote:
            k.VirtualFreeEx(handle, remote, 0, 0x8000)
        k.CloseHandle(handle)


def item_state(process, listview, row, state, mask):
    data = struct.pack("<IIIII", 0, 0, 0, state, mask) + bytes(96)
    assert send_remote(process.pid, listview, SET_ITEM_STATE, row, data)[0]


def verify_order(hwnd, changed, open_hidden=False):
    handle = toolbar(hwnd)
    assert handle and formatting_toolbar(hwnd)
    new_index = u.SendMessageW(handle, TB_COMMANDTOINDEX, NEW, 0)
    open_index = u.SendMessageW(handle, TB_COMMANDTOINDEX, OPEN, 0)
    assert new_index != -1 and open_index != -1
    assert (open_index < new_index) == changed
    assert bool(u.SendMessageW(handle, TB_ISBUTTONHIDDEN, NEW, 0)) == changed
    assert bool(u.SendMessageW(handle, TB_ISBUTTONHIDDEN, OPEN, 0)) == open_hidden


def show_dialog(process, hwnd, click=False):
    if click:
        handle = toolbar(hwnd)
        assert handle and u.IsWindowVisible(handle)
        button = u.SendMessageW(handle, TB_COMMANDTOINDEX, CUSTOMIZE, 0)
        result, raw = send_remote(process.pid, handle, TB_GETITEMRECT, button, bytes(16))
        left, top, right, bottom = struct.unpack("<iiii", raw)
        client = wt.RECT()
        assert result and u.GetClientRect(handle, c.byref(client))
        assert 0 <= left < right <= client.right and 0 <= top < bottom <= client.bottom
        at = ((top + bottom) // 2 << 16) | ((left + right) // 2)
        u.PostMessageW(handle, 0x201, 1, at)
        u.PostMessageW(handle, 0x202, 0, at)
    else:
        u.PostMessageW(hwnd, 0x111, CUSTOMIZE, 0)
    return wait_until(lambda: find_dialog(process, hwnd), "Main toolbar dialog did not open")


def close_dialog(process, hwnd, dialog, command):
    u.PostMessageW(dialog, 0x111, command, 0)
    wait_until(lambda: not find_dialog(process, hwnd), "Main toolbar dialog did not close")


def fresh(package, work):
    root = work / "fresh"
    shutil.copytree(package, root)
    exe = root / "NoteQu.exe"
    process, hwnd = launch(exe)
    try:
        assert command_label(hwnd, ABOUT) == "About NoteQu"
        assert command_label(hwnd, HOME) == "NoteQu Home"
        verify_order(hwnd, False)
        dialog = show_dialog(process, hwnd, click=True)
        assert "Customize Main Toolbar" in label_for_dialog(dialog)
        listview = u.GetDlgItem(dialog, LIST)
        item_state(process, listview, 0, 0x1000, 0xF000)  # Uncheck New.
        item_state(process, listview, 0, 0, 3)
        item_state(process, listview, 1, 3, 3)  # Select Open.
        u.SendMessageW(dialog, 0x111, UP, 0)
        close_dialog(process, hwnd, dialog, 1)
        wait_until(lambda: (root / CONFIG).is_file(), "Toolbar preference was not saved")
    finally:
        finish(exe, process)
    process, hwnd = launch(exe)
    try:
        verify_order(hwnd, True)
        dialog = show_dialog(process, hwnd)
        u.SendMessageW(dialog, 0x111, RESET, 0)
        close_dialog(process, hwnd, dialog, 2)
        verify_order(hwnd, True)
        dialog = show_dialog(process, hwnd)
        u.SendMessageW(dialog, 0x111, RESET, 0)
        close_dialog(process, hwnd, dialog, 1)
    finally:
        finish(exe, process)
    process, hwnd = launch(exe)
    try:
        verify_order(hwnd, False)
    finally:
        finish(exe, process)
    print("PASS: clean English package, visible button, reorder, hide, restart, cancel and reset")


def locale(package, work, language, about, home, dialog_name):
    root = work / language
    shutil.copytree(package, root)
    profile = root / "nativeLang.xml"
    cached = (root / "localization" / (language + ".xml")).read_bytes()
    # Use realistic stale profile labels regardless of the package's translations.
    for cmd in (ABOUT, HOME):
        start = cached.index(f'<Item id="{cmd}" name="'.encode())
        first = cached.index(b'name="', start) + len(b'name="')
        last = cached.index(b'"', first)
        cached = cached[:first] + b'Legacy Notepad++' + cached[last:]
    profile.write_bytes(cached)
    hidden = root / "toolbarButtonsConf.xml"
    legacy = b'<NotepadPlus><ToolbarButtons><Standard><Button id="41002" index="1" hide="yes"/></Standard></ToolbarButtons></NotepadPlus>'
    hidden.write_bytes(legacy)
    exe = root / "NoteQu.exe"
    process, hwnd = launch(exe)
    try:
        assert command_label(hwnd, ABOUT) == about
        assert command_label(hwnd, HOME) == home
        verify_order(hwnd, False, open_hidden=True)
        dialog = show_dialog(process, hwnd)
        assert dialog_name in label_for_dialog(dialog)
        close_dialog(process, hwnd, dialog, 2)
    finally:
        finish(exe, process)
    assert profile.read_bytes() == cached and hidden.read_bytes() == legacy
    print(f"PASS: {language} legacy labels, unchanged language and toolbar files, localized dialog")


def installed_plugin(package, work, archive):
    checksum = "cb415b51d78ff7d505d5966865bbba67216a00955462db0187448b06efedd50a"
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == checksum
    root = work / "with-plugin"
    shutil.copytree(package, root)
    plugin = root / "plugins" / "_CustomizeToolbar" / "_CustomizeToolbar.dll"
    plugin.parent.mkdir(parents=True)
    with zipfile.ZipFile(archive) as source:
        plugin.write_bytes(source.read(plugin.name))
    exe = root / "NoteQu.exe"
    process, hwnd = launch(exe)
    try:
        assert "Customize Toolbar..." in menus(hwnd)
        assert toolbar(hwnd) is None
        state = u.GetMenuState(u.GetMenu(hwnd), CUSTOMIZE, 0)
        assert state != 0xFFFFFFFF and state & 0x3
        assert formatting_toolbar(hwnd)
    finally:
        finish(exe, process)
    assert not (root / CONFIG).exists()
    print("PASS: Customize Toolbar 5.3 retains its own control and formatting customization remains available")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--package", type=Path, required=True)
    p.add_argument("--plugin-archive", type=Path)
    args = p.parse_args()
    with tempfile.TemporaryDirectory(prefix="notequ-windows-parity-") as directory:
        work = Path(directory)
        fresh(args.package, work)
        locale(args.package, work, "turkish", "NoteQu Hakk\u0131nda", "NoteQu Ana Sayfas\u0131",
               "Ana Ara\u00e7 \u00c7ubu\u011funu \u00d6zelle\u015ftir")
        locale(args.package, work, "spanish", "Acerca de NoteQu", "Sitio oficial de NoteQu",
               "Personalizar barra de herramientas principal")
        if args.plugin_archive:
            installed_plugin(args.package, work, args.plugin_archive)


if __name__ == "__main__":
    main()

