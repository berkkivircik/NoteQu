// Copyright (C) 2026 Berk Kivircik.
// SPDX-License-Identifier: GPL-3.0-only

#pragma once

#include "localization.h"
#include "menuCmdID.h"

namespace NoteQuProductUI {
struct Labels {
    const wchar_t *about, *home, *project, *mainToolbar, *hint, *up, *down,
        *reset, *apply, *cancel, *saveError;
};

inline const Labels &labels(const NativeLangSpeaker &language) {
    static constexpr Labels english{
        L"&About NoteQu", L"NoteQu &Home", L"NoteQu &Project Page",
        L"Customize Main Toolbar\u2026", L"Check the commands to show. Select a command to change its position.",
        L"Move &Up", L"Move &Down", L"&Restore Defaults", L"Apply", L"Cancel",
        L"Could not save the main toolbar settings."};
    static constexpr Labels turkish{
        L"NoteQu &Hakk\u0131nda", L"NoteQu &Ana Sayfas\u0131", L"NoteQu &Proje Sayfas\u0131",
        L"Ana Ara\u00e7 \u00c7ubu\u011funu \u00d6zelle\u015ftir\u2026",
        L"G\u00f6r\u00fcnecek komutlar\u0131 i\u015faretleyin. S\u0131ras\u0131n\u0131 de\u011fi\u015ftirmek i\u00e7in bir komut se\u00e7in.",
        L"&Yukar\u0131 ta\u015f\u0131", L"A\u015fa\u011f\u0131 &ta\u015f\u0131", L"&Varsay\u0131lana s\u0131f\u0131rla",
        L"Uygula", L"Vazge\u00e7", L"Ana ara\u00e7 \u00e7ubu\u011fu ayarlar\u0131 kaydedilemedi."};
    static constexpr Labels spanish{
        L"&Acerca de NoteQu", L"Sitio oficial de &NoteQu", L"P\u00e1gina del proyecto NoteQu",
        L"Personalizar barra de herramientas principal\u2026",
        L"Marca los comandos que quieres mostrar. Selecciona un comando para cambiar su posici\u00f3n.",
        L"&Subir", L"&Bajar", L"&Restaurar valores predeterminados", L"Aplicar", L"Cancelar",
        L"No se pudo guardar la configuraci\u00f3n de la barra de herramientas principal."};
    const char *file = language.getFileName();
    if (file && _stricmp(file, "turkish.xml") == 0)
        return turkish;
    if (file && _stricmp(file, "spanish.xml") == 0)
        return spanish;
    return english;
}

inline const wchar_t *menuLabel(unsigned long id, const NativeLangSpeaker &language) {
    const auto &text = labels(language);
    switch (id) {
    case IDM_ABOUT: return text.about;
    case IDM_HOMESWEETHOME: return text.home;
    case IDM_PROJECTPAGE: return text.project;
    case IDM_NOTEQU_MAIN_TOOLBAR: return text.mainToolbar;
    default: return nullptr;
    }
}

inline void applyMenuLabels(HMENU menu, const NativeLangSpeaker &language) {
    for (const auto id : {IDM_ABOUT, IDM_HOMESWEETHOME, IDM_PROJECTPAGE, IDM_NOTEQU_MAIN_TOOLBAR}) {
        MENUITEMINFOW item{sizeof(item)};
        item.fMask = MIIM_STRING;
        item.dwTypeData = const_cast<wchar_t *>(menuLabel(id, language));
        SetMenuItemInfoW(menu, id, FALSE, &item);
    }
}
} // namespace NoteQuProductUI
