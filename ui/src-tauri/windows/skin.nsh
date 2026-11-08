; EnhancedExtract installer skin: the app's dark cyberpunk look on top of Modern UI 2.
;
; Colours and type match theme.py and site/styles.css. Fonts ship inside the installer and
; are loaded privately (FR_PRIVATE): nothing is installed into Windows\Fonts.
;
; Native controls cannot be fully recoloured, so the skin:
;   - paints every page, label and edit field with SetCtlColors
;   - asks Windows for its dark control themes (DarkMode_Explorer / DarkMode_CFD)
;   - draws checkboxes and radio buttons without text and puts a clickable label next to
;     them, because themed check/radio text is always drawn black
;   - gives the progress bar a flat yellow fill

!include LogicLib.nsh
!include nsDialogs.nsh
!include WinMessages.nsh

!define /ifndef EE_SKIN_DIR "${__FILEDIR__}"

; RRGGBB for SetCtlColors
!define EE_BG      "0B0C12"
!define EE_FIELD   "171822"
!define EE_INK     "ECEADC"
!define EE_SOFT    "C6C6C0"
!define EE_MUTED   "8E8E9C"
!define EE_LINE    "262733"
!define EE_YELLOW  "FCEE0A"
!define EE_CYAN    "00E5F0"
; COLORREF (0x00BBGGRR) for Win32 messages
!define EE_REF_BG     0x00120C0B
!define EE_REF_FIELD  0x00221817
!define EE_REF_INK    0x00DCEAEC
!define EE_REF_YELLOW 0x000AEEFC

!define EE_FACE_DISPLAY "Oxanium"
!define EE_FACE_TEXT    "Bai Jamjuree"
!define EE_FACE_STRONG  "Bai Jamjuree SemiBold"

!define MUI_HEADERIMAGE_RIGHT
!define MUI_BGCOLOR   "${EE_BG}"
!define MUI_TEXTCOLOR "${EE_INK}"
!define MUI_CUSTOMFUNCTION_GUIINIT EE_GUIInit
!define MUI_CUSTOMFUNCTION_UNGUIINIT un.EE_GUIInit

!define /ifndef PBM_SETBARCOLOR 0x0409
!define /ifndef PBM_SETBKCOLOR  0x2001
!define /ifndef LVM_SETBKCOLOR     0x1001
!define /ifndef LVM_SETTEXTCOLOR   0x1024
!define /ifndef LVM_SETTEXTBKCOLOR 0x1026
!define /ifndef GWL_STYLE -16

!define /ifndef STM_SETIMAGE 0x0172
!define /ifndef WM_NCLBUTTONDOWN 0x00A1
!define EE_STATIC_BITMAP 0x5000010E   ; WS_CHILD | WS_VISIBLE | SS_NOTIFY | SS_BITMAP
!define EE_STATIC_TEXT   0x50000200   ; WS_CHILD | WS_VISIBLE | SS_CENTERIMAGE

; Frameless window (EE_Frameless): display scale of the chrome bitmaps (100/125/150/200),
; title bar height in px, and the bitmap statics that stand in for Back / Next / Cancel.
Var EE_Scale
Var EE_TitleH
Var EE_FakeBack
Var EE_FakeNext
Var EE_FakeCancel
Var EE_Exit

Var EE_FontBody
Var EE_FontStrong
Var EE_FontSmall
Var EE_FontHead
Var EE_FontTitle
Var EE_Hwnd
; Option labels of the reinstall page (installer.nsi, PageReinstall)
Var EE_Option1
Var EE_Option2

; Colour and font for one control.
!macro EE_STYLE HWND FONT FG BG
  SetCtlColors ${HWND} "${FG}" "${BG}"
  SendMessage ${HWND} ${WM_SETFONT} ${FONT} 1
!macroend
!define EE_Style "!insertmacro EE_STYLE"

!macro EE_DARK_THEME HWND CLASS
  System::Call 'uxtheme::SetWindowTheme(p ${HWND}, w "${CLASS}", p 0)'
!macroend

; A small yellow block, the bullet the site uses in lists.
!macro EE_BULLET X Y
  ${NSD_CreateLabel} ${X} ${Y} 4u 4u ""
  Pop $EE_Hwnd
  SetCtlColors $EE_Hwnd "" "${EE_YELLOW}"
!macroend
!define EE_Bullet "!insertmacro EE_BULLET"

; A 1px rule in the line colour.
!macro EE_RULE X Y W
  ${NSD_CreateLabel} ${X} ${Y} ${W} 1 ""
  Pop $EE_Hwnd
  SetCtlColors $EE_Hwnd "" "${EE_LINE}"
!macroend
!define EE_Rule "!insertmacro EE_RULE"

; Turn an etched separator of the outer window into a flat line in the line colour.
!macro EE_FLAT_LINE ID
  GetDlgItem $1 $HWNDPARENT ${ID}
  ; Drop SS_ETCHEDHORZ / SS_SUNKEN and any static edge, then let the frame redraw.
  System::Call 'user32::GetWindowLongW(p r1, i ${GWL_STYLE}) i .r2'
  IntOp $2 $2 & 0xFFFFEFE0
  System::Call 'user32::SetWindowLongW(p r1, i ${GWL_STYLE}, i r2)'
  System::Call 'user32::SetWindowLongW(p r1, i -20, i 0)'
  System::Call 'user32::SetWindowPos(p r1, p 0, i 0, i 0, i 0, i 0, i 0x37)'
  SetCtlColors $1 "" "${EE_LINE}"
!macroend
!define EE_FlatLine "!insertmacro EE_FLAT_LINE"

; Mirror the real Back / Next / Cancel onto the bitmap buttons: label, shown or hidden,
; enabled or dimmed. Called from every page's show function, and wherever a page changes
; a button's text.
!macro EE_SYNC_ONE ID FAKE DEFAULT
  GetDlgItem $1 $HWNDPARENT ${ID}
  System::Call 'user32::GetWindowTextW(p r1, w .r2, i 64)'
  StrCpy $3 "${DEFAULT}"
  ${Select} $2
  ${Case2} "Next >" "&Next >"
    StrCpy $3 "next"
  ${Case2} "< Back" "< &Back"
    StrCpy $3 "back"
  ${Case2} "Cancel" "&Cancel"
    StrCpy $3 "cancel"
  ${Case2} "Install" "&Install"
    StrCpy $3 "install"
  ${Case2} "Finish" "&Finish"
    StrCpy $3 "finish"
  ${Case2} "Close" "&Close"
    StrCpy $3 "close"
  ${Case2} "Uninstall" "&Uninstall"
    StrCpy $3 "uninstall"
  ${EndSelect}
  System::Call 'user32::IsWindowEnabled(p r1) i .r4'
  ${If} $4 <> 0
    StrCpy $4 "on"
  ${Else}
    StrCpy $4 "off"
  ${EndIf}
  System::Call 'user32::LoadImageW(p 0, w "$PLUGINSDIR\chrome\$3_$4_$EE_Scale.bmp", i 0, i 0, i 0, i 0x10) p .r5'
  SendMessage ${FAKE} ${STM_SETIMAGE} 0 $5 $6
  ${If} $6 <> 0
    System::Call 'gdi32::DeleteObject(p r6)'
  ${EndIf}
  ; The button's own WS_VISIBLE flag: IsWindowVisible is false for every control until the
  ; window itself shows, which is after the first page is built.
  System::Call 'user32::GetWindowLongW(p r1, i -16) i .r4'
  IntOp $4 $4 & 0x10000000
  ${If} $4 <> 0
    ShowWindow ${FAKE} ${SW_SHOW}
  ${Else}
    ShowWindow ${FAKE} ${SW_HIDE}
  ${EndIf}
!macroend

; Everything the installer and the uninstaller both need, defined once per prefix.
!macro EE_SKIN_FUNCTIONS UN

Function ${UN}EE_LoadFonts
  InitPluginsDir
  File "/oname=$PLUGINSDIR\ee-display.ttf" "${EE_SKIN_DIR}\fonts\oxanium-700.ttf"
  File "/oname=$PLUGINSDIR\ee-text.ttf" "${EE_SKIN_DIR}\fonts\bai-jamjuree-400.ttf"
  File "/oname=$PLUGINSDIR\ee-strong.ttf" "${EE_SKIN_DIR}\fonts\bai-jamjuree-600.ttf"
  System::Call 'gdi32::AddFontResourceExW(w "$PLUGINSDIR\ee-display.ttf", i 0x10, p 0)'
  System::Call 'gdi32::AddFontResourceExW(w "$PLUGINSDIR\ee-text.ttf", i 0x10, p 0)'
  System::Call 'gdi32::AddFontResourceExW(w "$PLUGINSDIR\ee-strong.ttf", i 0x10, p 0)'
  CreateFont $EE_FontBody "${EE_FACE_TEXT}" 9 400
  CreateFont $EE_FontStrong "${EE_FACE_STRONG}" 9 600
  CreateFont $EE_FontSmall "${EE_FACE_STRONG}" 7 600
  CreateFont $EE_FontHead "${EE_FACE_DISPLAY}" 11 700
  CreateFont $EE_FontTitle "${EE_FACE_DISPLAY}" 17 700
FunctionEnd

; Outer window: title bar, header, branding line and the Back / Next / Cancel buttons.
Function ${UN}EE_GUIInit
  Call ${UN}EE_LoadFonts

  ; Dark title bar, with a yellow window border and dark caption on Windows 11.
  System::Call 'dwmapi::DwmSetWindowAttribute(p $HWNDPARENT, i 20, *i 1, i 4)'
  System::Call 'dwmapi::DwmSetWindowAttribute(p $HWNDPARENT, i 34, *i ${EE_REF_YELLOW}, i 4)'
  System::Call 'dwmapi::DwmSetWindowAttribute(p $HWNDPARENT, i 35, *i ${EE_REF_BG}, i 4)'
  System::Call 'dwmapi::DwmSetWindowAttribute(p $HWNDPARENT, i 36, *i ${EE_REF_INK}, i 4)'

  SetCtlColors $HWNDPARENT "${EE_INK}" "${EE_BG}"
  ${EE_Style} $mui.Header.Text $EE_FontHead "${EE_YELLOW}" "${EE_BG}"
  ${EE_Style} $mui.Header.SubText $EE_FontBody "${EE_SOFT}" "${EE_BG}"
  ; The branding line is two disabled statics, which Windows draws embossed whatever the
  ; colours. Empty the back one and enable the front one so it takes the muted colour.
  SendMessage $mui.Branding.Background ${WM_SETTEXT} 0 "STR:"
  EnableWindow $mui.Branding.Text 1
  ${EE_Style} $mui.Branding.Text $EE_FontSmall "${EE_MUTED}" "${EE_BG}"

  ; The etched separators are drawn in light system colours; turn them into flat 1px lines.
  ${EE_FlatLine} 1035
  ${EE_FlatLine} 1045
  ${EE_FlatLine} 1036

  ${ForEach} $0 1 3 + 1
    GetDlgItem $1 $HWNDPARENT $0
    SetCtlColors $1 "${EE_INK}" "${EE_BG}"
    SendMessage $1 ${WM_SETFONT} $EE_FontStrong 1
    !insertmacro EE_DARK_THEME $1 "DarkMode_Explorer"
  ${Next}

  Call ${UN}EE_Frameless
FunctionEnd

; Like the app: no Windows frame. The window gets its own title bar (wordmark, what this is,
; a red EXIT) and cut-corner bitmap buttons in place of Back / Next / Cancel.
;
; The bitmap buttons are statics with the SAME control IDs as the real buttons (1 Next,
; 2 Cancel, 3 Back) and SS_NOTIFY. A click on a static sends WM_COMMAND(id, STN_CLICKED = 0),
; which is exactly what a click on the real button sends, so NSIS handles it as that button,
; including ignoring it while the real button is disabled. The real buttons stay alive (they
; hold the state and the default-button Enter key) but are moved out of sight. The statics
; are put at the bottom of the z-order so GetDlgItem keeps finding the real buttons.
Function ${UN}EE_Frameless
  ; Bitmaps for the display scale.
  System::Call 'user32::GetDpiForWindow(p $HWNDPARENT) i .r0'
  ${IfThen} $0 < 1 ${|} StrCpy $0 96 ${|}
  ${If} $0 <= 108
    StrCpy $EE_Scale 100
  ${ElseIf} $0 <= 132
    StrCpy $EE_Scale 125
  ${ElseIf} $0 <= 168
    StrCpy $EE_Scale 150
  ${Else}
    StrCpy $EE_Scale 200
  ${EndIf}
  IntOp $EE_TitleH $0 * 40
  IntOp $EE_TitleH $EE_TitleH / 96
  SetOutPath "$PLUGINSDIR\chrome"
  File "${EE_SKIN_DIR}\art\chrome\*.bmp"

  ; Everything moves down to make room for the title bar (client coordinates, so this is
  ; the same before and after the frame goes).
  StrCpy $5 0
  ${Do}
    FindWindow $5 "" "" $HWNDPARENT $5
    ${IfThen} $5 = 0 ${|} ${Break} ${|}
    System::Call '*(i,i,i,i) p .r6'
    System::Call 'user32::GetWindowRect(p r5, p r6)'
    System::Call 'user32::MapWindowPoints(p 0, p $HWNDPARENT, p r6, i 2)'
    System::Call '*$6(i .r7, i .r8)'
    System::Free $6
    IntOp $8 $8 + $EE_TitleH
    System::Call 'user32::SetWindowPos(p r5, p 0, i r7, i r8, i 0, i 0, i 0x15)'
  ${Loop}

  ; Drop the caption and the borders, then size the window to its old client area plus
  ; the title bar ($2 x $3), centred in the work area.
  System::Call '*(i,i,i,i) p .r1'
  System::Call 'user32::GetClientRect(p $HWNDPARENT, p r1)'
  System::Call '*$1(i, i, i .r2, i .r3)'
  System::Call 'user32::GetWindowLongW(p $HWNDPARENT, i -16) i .r4'
  IntOp $4 $4 & 0xFF3BFFFF
  System::Call 'user32::SetWindowLongW(p $HWNDPARENT, i -16, i r4)'
  System::Call 'user32::GetWindowLongW(p $HWNDPARENT, i -20) i .r4'
  IntOp $4 $4 & 0xFFFFFCFE
  System::Call 'user32::SetWindowLongW(p $HWNDPARENT, i -20, i r4)'
  IntOp $3 $3 + $EE_TitleH
  System::Call 'user32::SystemParametersInfoW(i 0x30, i 0, p r1, i 0)'
  System::Call '*$1(i .r4, i .r5, i .r6, i .r7)'
  System::Free $1
  IntOp $6 $6 + $4
  IntOp $6 $6 - $2
  IntOp $6 $6 / 2
  IntOp $7 $7 + $5
  IntOp $7 $7 - $3
  IntOp $7 $7 / 2
  System::Call 'user32::SetWindowPos(p $HWNDPARENT, p 0, i r6, i r7, i r2, i r3, i 0x24)'

  ; Title bar: wordmark | Setup ... EXIT, with a rule under it. $2 = window width.
  IntOp $8 $EE_Scale * 16
  IntOp $8 $8 / 100
  IntOp $9 $EE_Scale * 14
  IntOp $9 $9 / 100
  IntOp $9 $EE_TitleH - $9
  IntOp $9 $9 / 2
  System::Call 'user32::CreateWindowExW(i 0, w "STATIC", w "", i ${EE_STATIC_BITMAP}, i r8, i r9, i 0, i 0, p $HWNDPARENT, p 0, p 0, p 0) p .r4'
  System::Call 'user32::LoadImageW(p 0, w "$PLUGINSDIR\chrome\wordmark_$EE_Scale.bmp", i 0, i 0, i 0, i 0x10) p .r5'
  SendMessage $4 ${STM_SETIMAGE} 0 $5
  ; Separator and the window's name, after the wordmark.
  System::Call '*(i,i,i,i) p .r1'
  System::Call 'user32::GetWindowRect(p r4, p r1)'
  System::Call '*$1(i .r5, i, i .r6)'
  System::Free $1
  IntOp $6 $6 - $5
  IntOp $8 $8 + $6
  IntOp $5 $EE_Scale * 12
  IntOp $5 $5 / 100
  IntOp $8 $8 + $5
  IntOp $6 $EE_TitleH / 3
  IntOp $7 $EE_TitleH - $6
  IntOp $7 $7 / 2
  System::Call 'user32::CreateWindowExW(i 0, w "STATIC", w "", i 0x50000000, i r8, i r7, i 1, i r6, p $HWNDPARENT, p 0, p 0, p 0) p .r4'
  SetCtlColors $4 "" "3D3E4E"
  IntOp $8 $8 + $5
  IntOp $6 $EE_Scale * 120
  IntOp $6 $6 / 100
  !if "${UN}" == ""
    System::Call 'user32::CreateWindowExW(i 0, w "STATIC", w "Setup", i ${EE_STATIC_TEXT}, i r8, i 0, i r6, i $EE_TitleH, p $HWNDPARENT, p 0, p 0, p 0) p .r4'
  !else
    System::Call 'user32::CreateWindowExW(i 0, w "STATIC", w "Uninstall", i ${EE_STATIC_TEXT}, i r8, i 0, i r6, i $EE_TitleH, p $HWNDPARENT, p 0, p 0, p 0) p .r4'
  !endif
  ${EE_Style} $4 $EE_FontBody "${EE_INK}" "${EE_BG}"
  ; EXIT (ID 2 = Cancel; on pages where only Finish / Close is left, EE_SyncButtons gives it ID 1).
  IntOp $6 $EE_Scale * 58
  IntOp $6 $6 / 100
  IntOp $7 $EE_Scale * 26
  IntOp $7 $7 / 100
  IntOp $8 $EE_Scale * 12
  IntOp $8 $8 / 100
  IntOp $8 $2 - $8
  IntOp $8 $8 - $6
  IntOp $9 $EE_TitleH - $7
  IntOp $9 $9 / 2
  System::Call 'user32::CreateWindowExW(i 0, w "STATIC", w "", i ${EE_STATIC_BITMAP}, i r8, i r9, i 0, i 0, p $HWNDPARENT, p 2, p 0, p 0) p .r4'
  StrCpy $EE_Exit $4
  System::Call 'user32::LoadImageW(p 0, w "$PLUGINSDIR\chrome\exit_on_$EE_Scale.bmp", i 0, i 0, i 0, i 0x10) p .r5'
  SendMessage $4 ${STM_SETIMAGE} 0 $5
  System::Call 'user32::SetWindowPos(p r4, p 1, i 0, i 0, i 0, i 0, i 0x13)'
  IntOp $9 $EE_TitleH - 1
  System::Call 'user32::CreateWindowExW(i 0, w "STATIC", w "", i 0x50000000, i 0, i r9, i r2, i 1, p $HWNDPARENT, p 0, p 0, p 0) p .r4'
  SetCtlColors $4 "" "${EE_LINE}"

  ; Bottom buttons, right-aligned to where Cancel was, centred on its row. $6 x $7 = size.
  GetDlgItem $1 $HWNDPARENT 2
  System::Call '*(i,i,i,i) p .r3'
  System::Call 'user32::GetWindowRect(p r1, p r3)'
  System::Call 'user32::MapWindowPoints(p 0, p $HWNDPARENT, p r3, i 2)'
  System::Call '*$3(i, i .r4, i .r5, i .r9)'
  System::Free $3
  IntOp $6 $EE_Scale * 104
  IntOp $6 $6 / 100
  IntOp $7 $EE_Scale * 30
  IntOp $7 $7 / 100
  IntOp $9 $9 + $4
  IntOp $9 $9 - $7
  IntOp $9 $9 / 2
  IntOp $3 $EE_Scale * 8
  IntOp $3 $3 / 100
  IntOp $8 $5 - $6
  System::Call 'user32::CreateWindowExW(i 0, w "STATIC", w "", i ${EE_STATIC_BITMAP}, i r8, i r9, i 0, i 0, p $HWNDPARENT, p 2, p 0, p 0) p .r4'
  StrCpy $EE_FakeCancel $4
  IntOp $8 $8 - $3
  IntOp $8 $8 - $6
  System::Call 'user32::CreateWindowExW(i 0, w "STATIC", w "", i ${EE_STATIC_BITMAP}, i r8, i r9, i 0, i 0, p $HWNDPARENT, p 1, p 0, p 0) p .r4'
  StrCpy $EE_FakeNext $4
  IntOp $8 $8 - $3
  IntOp $8 $8 - $6
  System::Call 'user32::CreateWindowExW(i 0, w "STATIC", w "", i ${EE_STATIC_BITMAP}, i r8, i r9, i 0, i 0, p $HWNDPARENT, p 3, p 0, p 0) p .r4'
  StrCpy $EE_FakeBack $4
  ${ForEach} $0 1 3 + 1
    GetDlgItem $1 $HWNDPARENT $0
    System::Call 'user32::SetWindowPos(p r1, p 0, i -4000, i -4000, i 0, i 0, i 0x15)'
  ${Next}
  System::Call 'user32::SetWindowPos(p $EE_FakeCancel, p 1, i 0, i 0, i 0, i 0, i 0x13)'
  System::Call 'user32::SetWindowPos(p $EE_FakeNext, p 1, i 0, i 0, i 0, i 0, i 0x13)'
  System::Call 'user32::SetWindowPos(p $EE_FakeBack, p 1, i 0, i 0, i 0, i 0, i 0x13)'
FunctionEnd


Function ${UN}EE_SyncButtons
  Push $1
  Push $2
  Push $3
  Push $4
  Push $5
  Push $6
  !insertmacro EE_SYNC_ONE 3 $EE_FakeBack "back"
  !insertmacro EE_SYNC_ONE 1 $EE_FakeNext "next"
  !insertmacro EE_SYNC_ONE 2 $EE_FakeCancel "cancel"
  ; EXIT closes the window: as Cancel, or as Finish / Close where Cancel is no longer offered.
  GetDlgItem $1 $HWNDPARENT 2
  System::Call 'user32::IsWindowEnabled(p r1) i .r4'
  ${If} $4 <> 0
    System::Call 'user32::SetWindowLongW(p $EE_Exit, i -12, i 2)'
  ${Else}
    System::Call 'user32::SetWindowLongW(p $EE_Exit, i -12, i 1)'
  ${EndIf}
  Pop $6
  Pop $5
  Pop $4
  Pop $3
  Pop $2
  Pop $1
FunctionEnd

; Inner page: dark background, body font and dark themes for every control on it.
; Call it from a page's show function (or before nsDialogs::Show), then restyle the
; controls that need more than the default.
Function ${UN}EE_SkinPage
  Push $0
  Push $1
  Push $2
  Push $3
  FindWindow $0 "#32770" "" $HWNDPARENT
  SetCtlColors $0 "${EE_INK}" "${EE_BG}"
  ; The install pages' "Show details" is a plain Windows button; the progress bar says enough.
  GetDlgItem $1 $0 1027
  ${IfThen} $1 <> 0 ${|} ShowWindow $1 ${SW_HIDE} ${|}
  StrCpy $1 0
  ${Do}
    FindWindow $1 "" "" $0 $1
    ${IfThen} $1 = 0 ${|} ${Break} ${|}
    ; SetCtlColors keeps its colours in the window's user data: a control a page has
    ; already styled keeps its colours and font and only gets its dark theme.
    System::Call 'user32::GetWindowLongW(p r1, i -21) i .r3'
    System::Call 'user32::GetClassNameW(p r1, w .r2, i 64)'
    ${If} $3 <> 0
      ${Select} $2
      ${Case} "Edit"
        !insertmacro EE_DARK_THEME $1 "DarkMode_CFD"
      ${Case} "Button"
        !insertmacro EE_DARK_THEME $1 "DarkMode_Explorer"
      ${EndSelect}
      ${Continue}
    ${EndIf}
    ${Select} $2
    ${Case} "Edit"
      ${EE_Style} $1 $EE_FontBody "${EE_INK}" "${EE_FIELD}"
      !insertmacro EE_DARK_THEME $1 "DarkMode_CFD"
    ${Case} "msctls_progress32"
      ; Without a theme the bar takes our colours.
      System::Call 'uxtheme::SetWindowTheme(p r1, w "", w "")'
      SendMessage $1 ${PBM_SETBARCOLOR} 0 ${EE_REF_YELLOW}
      SendMessage $1 ${PBM_SETBKCOLOR} 0 ${EE_REF_FIELD}
    ${Case} "SysListView32"
      !insertmacro EE_DARK_THEME $1 "DarkMode_Explorer"
      SendMessage $1 ${WM_SETFONT} $EE_FontBody 1
      SendMessage $1 ${LVM_SETBKCOLOR} 0 ${EE_REF_FIELD}
      SendMessage $1 ${LVM_SETTEXTBKCOLOR} 0 ${EE_REF_FIELD}
      SendMessage $1 ${LVM_SETTEXTCOLOR} 0 0x00C0C6C6
    ${Case} "Button"
      ${EE_Style} $1 $EE_FontStrong "${EE_INK}" "${EE_BG}"
      !insertmacro EE_DARK_THEME $1 "DarkMode_Explorer"
    ${CaseElse}
      ${EE_Style} $1 $EE_FontBody "${EE_SOFT}" "${EE_BG}"
    ${EndSelect}
  ${Loop}
  Pop $3
  Pop $2
  Pop $1
  Pop $0
  Call ${UN}EE_SyncButtons
FunctionEnd

!macroend

; No title bar from Windows any more, so the window is moved by pressing on any empty part of
; a page: a transparent label under every other control. A static with SS_NOTIFY reports the
; press on mouse down, and handing that to the window as a caption press starts the move.
Function EE_Drag
  Pop $0
  System::Call 'user32::ReleaseCapture()'
  SendMessage $HWNDPARENT ${WM_NCLBUTTONDOWN} 2 0
FunctionEnd

!macro EE_DRAG_LAYER
  ${NSD_CreateLabel} 0 0 100% 100% ""
  Pop $EE_Hwnd
  SetCtlColors $EE_Hwnd "" transparent
  System::Call 'user32::SetWindowPos(p $EE_Hwnd, p 1, i 0, i 0, i 0, i 0, i 0x13)'
  ${NSD_OnClick} $EE_Hwnd EE_Drag
!macroend
!define EE_DragLayer "!insertmacro EE_DRAG_LAYER"

; Radio buttons and checkboxes look like the app's: the real control stays (it holds the
; state the pages read) but is hidden, and a bitmap static of the app's square box sits in
; its place, with the real control as its user data. EE_RefreshToggles redraws every box
; on the current page from its control's state.
Function EE_RefreshToggles
  Push $0
  Push $1
  Push $2
  Push $3
  Push $4
  Push $5
  FindWindow $0 "#32770" "" $HWNDPARENT
  StrCpy $1 0
  ${Do}
    FindWindow $1 "" "" $0 $1
    ${IfThen} $1 = 0 ${|} ${Break} ${|}
    System::Call 'user32::GetClassNameW(p r1, w .r2, i 16)'
    ${IfThen} $2 != "Static" ${|} ${Continue} ${|}
    System::Call 'user32::GetWindowLongW(p r1, i -16) i .r3'
    IntOp $3 $3 & 0x1F
    ${IfThen} $3 <> 14 ${|} ${Continue} ${|}
    nsDialogs::GetUserData $1
    Pop $2
    ${IfThen} "$2" == "" ${|} ${Continue} ${|}
    ${IfThen} $2 = 0 ${|} ${Continue} ${|}
    ; BS_RADIOBUTTON (4) / BS_AUTORADIOBUTTON (9) draw the radio; anything else the checkbox.
    System::Call 'user32::GetWindowLongW(p r2, i -16) i .r3'
    IntOp $3 $3 & 0xF
    SendMessage $2 ${BM_GETCHECK} 0 0 $4
    System::Call 'user32::IsWindowEnabled(p r2) i .r5'
    ${If} $3 = 4
    ${OrIf} $3 = 9
      ${If} $4 = ${BST_CHECKED}
        StrCpy $3 "radio_on"
      ${ElseIf} $5 <> 0
        StrCpy $3 "radio_off"
      ${Else}
        StrCpy $3 "radio_dis"
      ${EndIf}
    ${ElseIf} $4 = ${BST_CHECKED}
      StrCpy $3 "check_on"
    ${Else}
      StrCpy $3 "check_off"
    ${EndIf}
    System::Call 'user32::LoadImageW(p 0, w "$PLUGINSDIR\chrome\$3_$EE_Scale.bmp", i 0, i 0, i 0, i 0x10) p .r4'
    SendMessage $1 ${STM_SETIMAGE} 0 $4 $5
    ${If} $5 <> 0
      System::Call 'gdi32::DeleteObject(p r5)'
    ${EndIf}
  ${Loop}
  Pop $5
  Pop $4
  Pop $3
  Pop $2
  Pop $1
  Pop $0
FunctionEnd

; The box for real control REAL at X Y, next to its LABEL; a click on it runs HANDLER
; (which gets the box). The box is centred on the label's line of text (EE_AlignBox).
!macro EE_TOGGLE_BOX REAL LABEL X Y HANDLER
  Push ${LABEL}    ; first: LABEL may be $EE_Hwnd, which the next lines reuse
  nsDialogs::CreateControl STATIC ${EE_STATIC_BITMAP} 0 ${X} ${Y} 10u 10u ""
  Pop $EE_Hwnd
  nsDialogs::SetUserData $EE_Hwnd ${REAL}
  ${NSD_OnClick} $EE_Hwnd ${HANDLER}
  ShowWindow ${REAL} ${SW_HIDE}
  Push $EE_Hwnd
  Call EE_AlignBox
!macroend

; Stack: box, label. Centres the label's text vertically in the label, then gives the box its
; drawn size (radio 14 px, checkbox 16 px at 100 %) and centres it on the label's middle.
Function EE_AlignBox
  Exch $0          ; box
  Exch
  Exch $1          ; label
  Push $2
  Push $3
  Push $4
  Push $5
  Push $6
  System::Call 'user32::GetWindowLongW(p r1, i -16) i .r2'
  IntOp $2 $2 | 0x200
  System::Call 'user32::SetWindowLongW(p r1, i -16, i r2)'
  nsDialogs::GetUserData $0
  Pop $2
  System::Call 'user32::GetWindowLongW(p r2, i -16) i .r2'
  IntOp $2 $2 & 0xF
  ${If} $2 = 4
  ${OrIf} $2 = 9
    IntOp $3 $EE_Scale * 14
  ${Else}
    IntOp $3 $EE_Scale * 16
  ${EndIf}
  IntOp $3 $3 / 100
  System::Call 'user32::GetParent(p r0) p .r6'
  System::Call '*(i,i,i,i) p .r4'
  System::Call 'user32::GetWindowRect(p r1, p r4)'
  System::Call 'user32::MapWindowPoints(p 0, p r6, p r4, i 2)'
  System::Call '*$4(i, i .r5, i, i .r2)'
  IntOp $2 $2 - $5
  IntOp $2 $2 - $3
  IntOp $2 $2 / 2
  IntOp $5 $5 + $2
  System::Call 'user32::GetWindowRect(p r0, p r4)'
  System::Call 'user32::MapWindowPoints(p 0, p r6, p r4, i 2)'
  System::Call '*$4(i .r2)'
  System::Free $4
  System::Call 'user32::SetWindowPos(p r0, p 0, i r2, i r5, i r3, i r3, i 0x14)'
  Pop $6
  Pop $5
  Pop $4
  Pop $3
  Pop $2
  Pop $1
  Pop $0
FunctionEnd
!define EE_ToggleBox "!insertmacro EE_TOGGLE_BOX"

; Click handler for a checkbox's label or box: the real checkbox is the clicked control's
; user data. Installer only: the uninstaller's one checkbox is on a built-in page.
Function EE_ToggleFromLabel
  Pop $0
  nsDialogs::GetUserData $0
  Pop $0
  ${NSD_GetState} $0 $1
  ${If} $1 == ${BST_CHECKED}
    ${NSD_Uncheck} $0
  ${Else}
    ${NSD_Check} $0
  ${EndIf}
  Call EE_RefreshToggles
FunctionEnd

; Checkbox drawn as a dark box plus a clickable label (themed check text is always black).
; Leaves the checkbox hwnd in VAR and the label in $EE_Hwnd. LX/LY place the label.
!macro EE_CHECKBOX VAR X Y LX LY W TEXT CHECKED
  ${NSD_CreateCheckbox} ${X} ${Y} 10u 10u ""
  Pop ${VAR}
  ${If} ${CHECKED} == 1
    ${NSD_Check} ${VAR}
  ${EndIf}
  ${NSD_CreateLabel} ${LX} ${LY} ${W} 10u "${TEXT}"
  Pop $EE_Hwnd
  nsDialogs::SetUserData $EE_Hwnd ${VAR}
  ${NSD_OnClick} $EE_Hwnd EE_ToggleFromLabel
  Push $EE_Hwnd
  ${EE_ToggleBox} ${VAR} $EE_Hwnd ${X} ${Y} EE_ToggleFromLabel
  Pop $EE_Hwnd
!macroend
