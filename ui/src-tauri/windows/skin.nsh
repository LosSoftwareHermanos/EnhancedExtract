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
FunctionEnd

!macroend

; Label click handler for a checkbox: the hwnd of the box is the label's user data.
; Installer only: the uninstaller's one checkbox is on a built-in page without nsDialogs.
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
!macroend
