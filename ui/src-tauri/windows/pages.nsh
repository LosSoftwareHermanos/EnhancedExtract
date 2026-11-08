; EnhancedExtract installer pages: Welcome, install options and Finish layouts, plus the
; label click handler of the reinstall page. Included by installer.nsi after its page
; declarations; page callbacks are resolved once the whole script is read.
;
; Dialog units (u) scale with the system font and DPI. Welcome / Finish content sits right
; of the 109u sidebar art; header pages have about 300u x 140u.

!insertmacro EE_SKIN_FUNCTIONS ""
!insertmacro EE_SKIN_FUNCTIONS "un."

Var EE_DirField
Var EE_ContextBox
Var EE_DesktopBox
Var EE_RunBox
Var EE_RunAfterFinish

; ---------------------------------------------------------------------------------------
; Shared layout pieces

; Small coloured capitals above a group, like the site's section labels.
!macro EE_KICKER X Y W TEXT COLOR
  ${NSD_CreateLabel} ${X} ${Y} ${W} 10u "${TEXT}"
  Pop $EE_Hwnd
  ${EE_Style} $EE_Hwnd $EE_FontSmall "${COLOR}" "${EE_BG}"
!macroend

; Bullet + one line of text. Y is in dialog units (a number). The text is centred in its
; 12u row and the 4u bullet sits 4u down, so both share the row's middle.
!macro EE_POINT Y TEXT
  !define /math EE_POINT_BY ${Y} + 4
  ${EE_Bullet} 120u ${EE_POINT_BY}u
  !undef EE_POINT_BY
  ${NSD_CreateLabel} 130u ${Y}u 185u 12u "${TEXT}"
  Pop $EE_Hwnd
  ${EE_Style} $EE_Hwnd $EE_FontBody "${EE_SOFT}" "${EE_BG}"
  System::Call 'user32::GetWindowLongW(p $EE_Hwnd, i -16) i .s'
  Exch $0
  IntOp $0 $0 | 0x200
  System::Call 'user32::SetWindowLongW(p $EE_Hwnd, i -16, i r0)'
  Pop $0
!macroend

; Title in two lines: white then yellow.
!macro EE_TITLE LINE1 LINE2
  ${NSD_CreateLabel} 120u 24u 195u 17u "${LINE1}"
  Pop $EE_Hwnd
  ${EE_Style} $EE_Hwnd $EE_FontTitle "${EE_INK}" "${EE_BG}"
  ${NSD_CreateLabel} 120u 40u 195u 17u "${LINE2}"
  Pop $EE_Hwnd
  ${EE_Style} $EE_Hwnd $EE_FontTitle "${EE_YELLOW}" "${EE_BG}"
!macroend

; Hide the stock title / text of a Modern UI welcome or finish page; we draw our own.
!macro EE_HIDE_STOCK TITLE TEXT
  ShowWindow ${TITLE} ${SW_HIDE}
  ShowWindow ${TEXT} ${SW_HIDE}
!macroend

; ---------------------------------------------------------------------------------------
; Welcome

Function EE_WelcomeShow
  !insertmacro EE_HIDE_STOCK $mui.WelcomePage.Title $mui.WelcomePage.Text

  !insertmacro EE_KICKER 120u 12u 195u "SETUP  //  V${VERSION}  //  WINDOWS 10/11" "${EE_CYAN}"
  !insertmacro EE_TITLE "Install" "${PRODUCTNAME}"

  ${NSD_CreateLabel} 120u 61u 192u 40u "Extracts RAR, ZIP and 7z sets and installs game ISOs, deleting parts as it goes, so big downloads never need double the space."
  Pop $EE_Hwnd
  ${EE_Style} $EE_Hwnd $EE_FontBody "${EE_SOFT}" "${EE_BG}"

  ${EE_Rule} 120u 104u 190u
  !insertmacro EE_KICKER 120u 110u 195u "WHAT THIS SETUP DOES" "${EE_YELLOW}"
  !insertmacro EE_POINT 124 "Start menu shortcut and right-click menu."
  !insertmacro EE_POINT 137 "UnRAR + 7-Zip built in. No bundled offers."
  !insertmacro EE_POINT 150 "Uninstall any time in Settings > Apps."

  ${NSD_CreateLabel} 120u 180u 195u 10u "Click Next to choose where it goes."
  Pop $EE_Hwnd
  ${EE_Style} $EE_Hwnd $EE_FontSmall "${EE_MUTED}" "${EE_BG}"

  ${EE_DragLayer}
  Call EE_SyncButtons
FunctionEnd

; ---------------------------------------------------------------------------------------
; Install options: folder, right-click menu, desktop shortcut

Function EE_InitOptions
  StrCpy $EE_ContextMenu 1
  StrCpy $EE_DesktopShortcut 1
  ; On a reinstall or upgrade keep what the user chose last time.
  ReadRegStr $0 SHCTX "${UNINSTKEY}" "UninstallString"
  ${If} $0 != ""
    ReadRegStr $0 HKCU "Software\Classes\SystemFileAssociations\.rar\shell\EnhancedExtract" "MUIVerb"
    ${IfThen} $0 == "" ${|} StrCpy $EE_ContextMenu 0 ${|}
    ${IfNot} ${FileExists} "$DESKTOP\${PRODUCTNAME}.lnk"
      StrCpy $EE_DesktopShortcut 0
    ${EndIf}
  ${EndIf}
FunctionEnd

Function EE_OptionsPage
  ${IfThen} $PassiveMode = 1 ${|} Abort ${|}
  !insertmacro MUI_HEADER_TEXT "Install options" "Pick a folder and what to add to Windows."

  nsDialogs::Create 1018
  Pop $0
  ${IfThen} $0 == error ${|} Abort ${|}

  !insertmacro EE_KICKER 0 0 100% "INSTALL LOCATION" "${EE_YELLOW}"
  ${NSD_CreateDirRequest} 0 11u 226u 18u "$INSTDIR"
  Pop $EE_DirField
  nsDialogs::CreateControl STATIC ${EE_STATIC_BITMAP} 0 232u 11u 68u 18u ""
  Pop $0
  System::Call 'user32::LoadImageW(p 0, w "$PLUGINSDIR\chrome\browse_on_$EE_Scale.bmp", i 0, i 0, i 0, i 0x10) p .r1'
  SendMessage $0 ${STM_SETIMAGE} 0 $1
  ${NSD_OnClick} $0 EE_BrowseFolder

  IntOp $1 ${ESTIMATEDSIZE} / 1024
  ${NSD_CreateLabel} 0 34u 100% 10u "About $1 MB, in your user profile. No admin rights needed to install."
  Pop $EE_Hwnd
  ${EE_Style} $EE_Hwnd $EE_FontBody "${EE_MUTED}" "${EE_BG}"

  ${EE_Rule} 0 49u 100%
  !insertmacro EE_KICKER 0 54u 100% "ADD TO WINDOWS" "${EE_YELLOW}"

  !insertmacro EE_CHECKBOX $EE_ContextBox 0 66u 14u 67u 280u "Right-click menu for archives" $EE_ContextMenu
  ${EE_Style} $EE_Hwnd $EE_FontStrong "${EE_INK}" "${EE_BG}"
  ${NSD_CreateLabel} 14u 78u 286u 10u ".rar, .zip, .7z and 20 more. Your default archive app stays."
  Pop $EE_Hwnd
  ${EE_Style} $EE_Hwnd $EE_FontBody "${EE_MUTED}" "${EE_BG}"

  !insertmacro EE_CHECKBOX $EE_DesktopBox 0 92u 14u 93u 280u "Desktop shortcut" $EE_DesktopShortcut
  ${EE_Style} $EE_Hwnd $EE_FontStrong "${EE_INK}" "${EE_BG}"

  ${EE_Rule} 0 109u 100%
  ${NSD_CreateLabel} 0 114u 100% 24u "The app runs as administrator, which ISO installs need, so Windows asks to confirm when you open it. Right-click extraction runs without admin."
  Pop $EE_Hwnd
  ${EE_Style} $EE_Hwnd $EE_FontBody "${EE_MUTED}" "${EE_BG}"

  ${EE_DragLayer}
  Call EE_SkinPage
  Call EE_RefreshToggles

  ${NSD_SetFocus} $EE_DirField
  nsDialogs::Show
FunctionEnd

Function EE_BrowseFolder
  Pop $0
  ${NSD_GetText} $EE_DirField $1
  nsDialogs::SelectFolderDialog "Choose the folder to install ${PRODUCTNAME} in" "$1"
  Pop $0
  ${If} $0 != error
    ; Like the stock directory page: picking D:\Apps installs to D:\Apps\EnhancedExtract.
    StrLen $1 "${PRODUCTNAME}"
    IntOp $1 0 - $1
    StrCpy $2 $0 "" $1
    ${If} $2 != "${PRODUCTNAME}"
      StrCpy $3 $0 1 -1
      ${IfThen} $3 == "\" ${|} StrCpy $0 $0 -1 ${|}
      StrCpy $0 "$0\${PRODUCTNAME}"
    ${EndIf}
    ${NSD_SetText} $EE_DirField $0
  ${EndIf}
FunctionEnd

Function EE_OptionsLeave
  ${NSD_GetText} $EE_DirField $0
  ; Needs a full path such as C:\... or \\server\share\...
  StrCpy $1 $0 2 1
  StrCpy $2 $0 2
  ${If} $1 != ":\"
  ${AndIf} $2 != "\\"
    MessageBox MB_ICONEXCLAMATION "Choose a full folder path, for example $LOCALAPPDATA\${PRODUCTNAME}."
    Abort
  ${EndIf}
  StrCpy $INSTDIR $0
  ${NSD_GetState} $EE_ContextBox $EE_ContextMenu
  ${NSD_GetState} $EE_DesktopBox $EE_DesktopShortcut
FunctionEnd

; ---------------------------------------------------------------------------------------
; Reinstall / upgrade page: clicking an option's label selects its radio button.

Function EE_ReinstallLabelClick
  Pop $0
  nsDialogs::GetUserData $0
  Pop $0
  ; The radio itself says whether this choice is allowed (a downgrade can turn one off).
  System::Call 'user32::IsWindowEnabled(p r0) i .r1'
  ${IfThen} $1 = 0 ${|} Return ${|}
  ${If} $0 == $R2
    ${NSD_Check} $R2
    ${NSD_Uncheck} $R3
  ${Else}
    ${NSD_Check} $R3
    ${NSD_Uncheck} $R2
  ${EndIf}
  Call PageReinstallUpdateSelection
  Call EE_RefreshToggles
FunctionEnd

; ---------------------------------------------------------------------------------------
; Finish

Function EE_FinishShow
  !insertmacro EE_HIDE_STOCK $mui.FinishPage.Title $mui.FinishPage.Text

  !insertmacro EE_KICKER 120u 12u 195u "DONE  //  V${VERSION}" "${EE_CYAN}"
  !insertmacro EE_TITLE "Installed." "Ready to extract."

  ${NSD_CreateLabel} 120u 61u 192u 40u "Point its Library at your downloads folder and it lists every archive set and ISO it finds there."
  Pop $EE_Hwnd
  ${EE_Style} $EE_Hwnd $EE_FontBody "${EE_SOFT}" "${EE_BG}"

  ${EE_Rule} 120u 104u 190u
  !insertmacro EE_KICKER 120u 110u 195u "WHERE TO FIND IT" "${EE_YELLOW}"
  !insertmacro EE_POINT 124 "Start menu > ${PRODUCTNAME}"
  ${If} $EE_ContextMenu = 1
    !insertmacro EE_POINT 137 "Right-click any archive > ${PRODUCTNAME}"
  ${EndIf}

  !insertmacro EE_CHECKBOX $EE_RunBox 120u 160u 134u 161u 180u "Open ${PRODUCTNAME} now" 1
  ${EE_Style} $EE_RunBox $EE_FontBody "${EE_INK}" "${EE_BG}"
  !insertmacro EE_DARK_THEME $EE_RunBox "DarkMode_Explorer"
  ${EE_Style} $EE_Hwnd $EE_FontStrong "${EE_INK}" "${EE_BG}"

  ${EE_DragLayer}
  Call EE_RefreshToggles
  Call EE_SyncButtons
FunctionEnd

Function EE_FinishLeave
  ${NSD_GetState} $EE_RunBox $EE_RunAfterFinish
  ${If} $EE_RunAfterFinish == ${BST_CHECKED}
    Call RunMainBinary
  ${EndIf}
FunctionEnd
