from leond import hotkey


def test_fenn_shortcut_constants_are_available() -> None:
    assert hotkey.MOD_CONTROL == 0x0002
    assert hotkey.VK_N == 0x4E
    assert hotkey.VK_SPACE == 0x20


def test_binding_keeps_name_mods_and_key() -> None:
    binding = hotkey.Binding(
        "Ctrl+Alt+N", hotkey.MOD_CONTROL | hotkey.MOD_ALT, hotkey.VK_N, lambda: None
    )
    assert binding.name == "Ctrl+Alt+N"
    assert binding.mods == hotkey.MOD_CONTROL | hotkey.MOD_ALT
    assert binding.vk == hotkey.VK_N
