; The installer template (installer.nsi) lives next to this file; it includes pages.nsh
; from here, and the skin is loaded first so every page can use it.
!define EE_WINDOWS_DIR "${__FILEDIR__}"
!include "${EE_WINDOWS_DIR}\skin.nsh"

; Install options, set on the options page (pages.nsh). 1 = yes.
Var EE_ContextMenu
Var EE_DesktopShortcut

; Add a collapsible "EnhancedExtract" submenu for archives without changing the user's
; default archive application. Registered under SystemFileAssociations so it only
; appears on those file types and needs no AppliesTo filter.
;
; .rar goes to UnRAR; every other format below goes to 7-Zip inside the engine.
; Keep this list in step with OTHER_EXTS in src/shell.rs and SINGLE_EXTS in sevenzip.py.
!macro EE_MENU_ADD EXT FREELABEL
  DeleteRegKey HKCU "Software\Classes\SystemFileAssociations\${EXT}\shell\EnhancedExtractFree"
  DeleteRegKey HKCU "Software\Classes\SystemFileAssociations\${EXT}\shell\EnhancedExtract1"
  DeleteRegKey HKCU "Software\Classes\SystemFileAssociations\${EXT}\shell\EnhancedExtract2"
  DeleteRegKey HKCU "Software\Classes\SystemFileAssociations\${EXT}\shell\EnhancedExtract3"
  DeleteRegKey HKCU "Software\Classes\SystemFileAssociations\${EXT}\shell\EnhancedExtract"
  WriteRegStr HKCU "Software\Classes\SystemFileAssociations\${EXT}\shell\EnhancedExtract" "MUIVerb" "EnhancedExtract"
  WriteRegStr HKCU "Software\Classes\SystemFileAssociations\${EXT}\shell\EnhancedExtract" "Icon" '"$INSTDIR\${MAINBINARYNAME}.exe",0'
  WriteRegStr HKCU "Software\Classes\SystemFileAssociations\${EXT}\shell\EnhancedExtract" "SubCommands" ""
  WriteRegStr HKCU "Software\Classes\SystemFileAssociations\${EXT}\shell\EnhancedExtract\shell\1extract" "" "Extract with EnhancedExtract"
  WriteRegStr HKCU "Software\Classes\SystemFileAssociations\${EXT}\shell\EnhancedExtract\shell\1extract" "Icon" '"$INSTDIR\${MAINBINARYNAME}.exe",0'
  WriteRegStr HKCU "Software\Classes\SystemFileAssociations\${EXT}\shell\EnhancedExtract\shell\1extract\command" "" '"$INSTDIR\${MAINBINARYNAME}.exe" --shell-extract "%1"'
  WriteRegStr HKCU "Software\Classes\SystemFileAssociations\${EXT}\shell\EnhancedExtract\shell\2free" "" "${FREELABEL}"
  WriteRegStr HKCU "Software\Classes\SystemFileAssociations\${EXT}\shell\EnhancedExtract\shell\2free" "Icon" '"$INSTDIR\${MAINBINARYNAME}.exe",0'
  WriteRegStr HKCU "Software\Classes\SystemFileAssociations\${EXT}\shell\EnhancedExtract\shell\2free\command" "" '"$INSTDIR\${MAINBINARYNAME}.exe" --shell-extract-delete "%1"'
  WriteRegStr HKCU "Software\Classes\SystemFileAssociations\${EXT}\shell\EnhancedExtract\shell\3open" "" "Open with EnhancedExtract"
  WriteRegStr HKCU "Software\Classes\SystemFileAssociations\${EXT}\shell\EnhancedExtract\shell\3open" "Icon" '"$INSTDIR\${MAINBINARYNAME}.exe",0'
  WriteRegStr HKCU "Software\Classes\SystemFileAssociations\${EXT}\shell\EnhancedExtract\shell\3open\command" "" '"$INSTDIR\${MAINBINARYNAME}.exe" --open "%1"'
!macroend

; Register the same archive submenu under a file's active ProgID as well. Windows
; checks the ProgID before SystemFileAssociations for some formats such as ZIP.
!macro EE_MENU_ADD_PROGID PROGID FREELABEL
  DeleteRegKey HKCU "Software\Classes\${PROGID}\shell\EnhancedExtract"
  WriteRegStr HKCU "Software\Classes\${PROGID}\shell\EnhancedExtract" "MUIVerb" "EnhancedExtract"
  WriteRegStr HKCU "Software\Classes\${PROGID}\shell\EnhancedExtract" "Icon" '"$INSTDIR\${MAINBINARYNAME}.exe",0'
  WriteRegStr HKCU "Software\Classes\${PROGID}\shell\EnhancedExtract" "SubCommands" ""
  WriteRegStr HKCU "Software\Classes\${PROGID}\shell\EnhancedExtract" "EEOwner" "com.lossoftwarehermanos.EnhancedExtract"
  WriteRegStr HKCU "Software\Classes\${PROGID}\shell\EnhancedExtract\shell\1extract" "" "Extract with EnhancedExtract"
  WriteRegStr HKCU "Software\Classes\${PROGID}\shell\EnhancedExtract\shell\1extract" "Icon" '"$INSTDIR\${MAINBINARYNAME}.exe",0'
  WriteRegStr HKCU "Software\Classes\${PROGID}\shell\EnhancedExtract\shell\1extract\command" "" '"$INSTDIR\${MAINBINARYNAME}.exe" --shell-extract "%1"'
  WriteRegStr HKCU "Software\Classes\${PROGID}\shell\EnhancedExtract\shell\2free" "" "${FREELABEL}"
  WriteRegStr HKCU "Software\Classes\${PROGID}\shell\EnhancedExtract\shell\2free" "Icon" '"$INSTDIR\${MAINBINARYNAME}.exe",0'
  WriteRegStr HKCU "Software\Classes\${PROGID}\shell\EnhancedExtract\shell\2free\command" "" '"$INSTDIR\${MAINBINARYNAME}.exe" --shell-extract-delete "%1"'
  WriteRegStr HKCU "Software\Classes\${PROGID}\shell\EnhancedExtract\shell\3open" "" "Open with EnhancedExtract"
  WriteRegStr HKCU "Software\Classes\${PROGID}\shell\EnhancedExtract\shell\3open" "Icon" '"$INSTDIR\${MAINBINARYNAME}.exe",0'
  WriteRegStr HKCU "Software\Classes\${PROGID}\shell\EnhancedExtract\shell\3open\command" "" '"$INSTDIR\${MAINBINARYNAME}.exe" --open "%1"'
!macroend

!macro EE_MENU_ADD_ACTIVE_PROGID EXT VALUE_NAME FREELABEL
  ReadRegStr $R0 HKCR "${EXT}" ""
  ${If} $R0 != ""
    ReadRegStr $R2 HKCU "Software\Classes\$R0\shell\EnhancedExtract" "EEOwner"
    ${If} $R2 == "com.lossoftwarehermanos.EnhancedExtract"
      !insertmacro EE_MENU_ADD_PROGID "$R0" "${FREELABEL}"
      WriteRegStr HKCU "Software\EnhancedExtract\ShellIntegration" "${VALUE_NAME}" "$R0"
    ${Else}
      ReadRegStr $R2 HKCU "Software\Classes\$R0\shell\EnhancedExtract" "MUIVerb"
      ${If} $R2 == ""
        !insertmacro EE_MENU_ADD_PROGID "$R0" "${FREELABEL}"
        WriteRegStr HKCU "Software\EnhancedExtract\ShellIntegration" "${VALUE_NAME}" "$R0"
      ${EndIf}
    ${EndIf}
  ${EndIf}
!macroend

!macro EE_ISO_ADD_ROOT ROOT
  DeleteRegKey HKCU "${ROOT}\shell\EnhancedExtractISO"
  WriteRegStr HKCU "${ROOT}\shell\EnhancedExtractISO" "" "Set up ISO with EnhancedExtract..."
  WriteRegStr HKCU "${ROOT}\shell\EnhancedExtractISO" "Icon" '"$INSTDIR\${MAINBINARYNAME}.exe",0'
  WriteRegStr HKCU "${ROOT}\shell\EnhancedExtractISO" "EEOwner" "com.lossoftwarehermanos.EnhancedExtract"
  WriteRegStr HKCU "${ROOT}\shell\EnhancedExtractISO\command" "" '"$INSTDIR\${MAINBINARYNAME}.exe" --open "%1"'
!macroend

!macro EE_ISO_ADD_ACTIVE_PROGID
  ReadRegStr $R0 HKCR ".iso" ""
  ${If} $R0 != ""
    ReadRegStr $R2 HKCU "Software\Classes\$R0\shell\EnhancedExtractISO" "EEOwner"
    ${If} $R2 == "com.lossoftwarehermanos.EnhancedExtract"
      !insertmacro EE_ISO_ADD_ROOT "Software\Classes\$R0"
      WriteRegStr HKCU "Software\EnhancedExtract\ShellIntegration" "IsoProgID" "$R0"
    ${Else}
      ReadRegStr $R2 HKCU "Software\Classes\$R0\shell\EnhancedExtractISO" ""
      ${If} $R2 == ""
        !insertmacro EE_ISO_ADD_ROOT "Software\Classes\$R0"
        WriteRegStr HKCU "Software\EnhancedExtract\ShellIntegration" "IsoProgID" "$R0"
      ${EndIf}
    ${EndIf}
  ${EndIf}
!macroend

!macro EE_MENU_REMOVE_TRACKED_PROGID VALUE_NAME VERB
  ReadRegStr $R0 HKCU "Software\EnhancedExtract\ShellIntegration" "${VALUE_NAME}"
  ${If} $R0 != ""
    ReadRegStr $R2 HKCU "Software\Classes\$R0\shell\${VERB}" "EEOwner"
    ${If} $R2 == "com.lossoftwarehermanos.EnhancedExtract"
      DeleteRegKey HKCU "Software\Classes\$R0\shell\${VERB}"
    ${EndIf}
    DeleteRegValue HKCU "Software\EnhancedExtract\ShellIntegration" "${VALUE_NAME}"
  ${EndIf}
  DeleteRegKey /ifempty HKCU "Software\EnhancedExtract\ShellIntegration"
!macroend

!macro EE_MENU_REMOVE EXT
  DeleteRegKey HKCU "Software\Classes\SystemFileAssociations\${EXT}\shell\EnhancedExtract"
!macroend

!macro NSIS_HOOK_POSTINSTALL
  DeleteRegKey HKCU "Software\Classes\*\shell\EnhancedExtract"
  DeleteRegKey HKCU "Software\Classes\*\shell\EnhancedExtractFree"
  ${If} $EE_ContextMenu <> 1
    !insertmacro EE_MENU_REMOVE_ALL
  ${Else}
  !insertmacro EE_MENU_REMOVE_TRACKED_PROGID "ZipProgID" "EnhancedExtract"
  !insertmacro EE_MENU_REMOVE_TRACKED_PROGID "IsoProgID" "EnhancedExtractISO"
  !insertmacro EE_MENU_ADD ".rar" "Extract and free space (delete parts)..."
  !insertmacro EE_MENU_ADD ".zip" "Extract and free space (delete archive)..."
  !insertmacro EE_MENU_ADD ".zipx" "Extract and free space (delete archive)..."
  !insertmacro EE_MENU_ADD ".7z" "Extract and free space (delete archive)..."
  !insertmacro EE_MENU_ADD ".001" "Extract and free space (delete parts)..."
  !insertmacro EE_MENU_ADD ".tar" "Extract and free space (delete archive)..."
  !insertmacro EE_MENU_ADD ".gz" "Extract and free space (delete archive)..."
  !insertmacro EE_MENU_ADD ".tgz" "Extract and free space (delete archive)..."
  !insertmacro EE_MENU_ADD ".bz2" "Extract and free space (delete archive)..."
  !insertmacro EE_MENU_ADD ".tbz" "Extract and free space (delete archive)..."
  !insertmacro EE_MENU_ADD ".tbz2" "Extract and free space (delete archive)..."
  !insertmacro EE_MENU_ADD ".xz" "Extract and free space (delete archive)..."
  !insertmacro EE_MENU_ADD ".txz" "Extract and free space (delete archive)..."
  !insertmacro EE_MENU_ADD ".zst" "Extract and free space (delete archive)..."
  !insertmacro EE_MENU_ADD ".tzst" "Extract and free space (delete archive)..."
  !insertmacro EE_MENU_ADD ".lzma" "Extract and free space (delete archive)..."
  !insertmacro EE_MENU_ADD ".z" "Extract and free space (delete archive)..."
  !insertmacro EE_MENU_ADD ".arj" "Extract and free space (delete archive)..."
  !insertmacro EE_MENU_ADD ".lzh" "Extract and free space (delete archive)..."
  !insertmacro EE_MENU_ADD ".lha" "Extract and free space (delete archive)..."
  !insertmacro EE_MENU_ADD ".cpio" "Extract and free space (delete archive)..."
  !insertmacro EE_MENU_ADD ".cab" "Extract and free space (delete archive)..."
  !insertmacro EE_MENU_ADD ".wim" "Extract and free space (delete archive)..."
  !insertmacro EE_MENU_ADD_ACTIVE_PROGID ".zip" "ZipProgID" "Extract and free space (delete archive)..."
  !insertmacro EE_ISO_ADD_ROOT "Software\Classes\SystemFileAssociations\.iso"
  !insertmacro EE_ISO_ADD_ACTIVE_PROGID
  ${EndIf}
  ; Shortcuts launch the dashboard as administrator (needed for ISO install). The
  ; right-click extract entries run the exe directly and stay unelevated.
  nsExec::Exec `powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "foreach($$p in \"$SMPROGRAMS\${PRODUCTNAME}.lnk\",\"$DESKTOP\${PRODUCTNAME}.lnk\"){ if(Test-Path $$p){ $$b=[IO.File]::ReadAllBytes($$p); $$b[0x15]=$$b[0x15] -bor 0x20; [IO.File]::WriteAllBytes($$p,$$b) } }"`
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  DeleteRegKey HKCU "Software\Classes\*\shell\EnhancedExtract"
  DeleteRegKey HKCU "Software\Classes\*\shell\EnhancedExtractFree"
  !insertmacro EE_MENU_REMOVE_ALL
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
!macroend

; Every extension EE_MENU_ADD registers (used on uninstall and when the option is off).
!macro EE_MENU_REMOVE_ALL
  !insertmacro EE_MENU_REMOVE_TRACKED_PROGID "ZipProgID" "EnhancedExtract"
  !insertmacro EE_MENU_REMOVE_TRACKED_PROGID "IsoProgID" "EnhancedExtractISO"
  !insertmacro EE_MENU_REMOVE ".rar"
  !insertmacro EE_MENU_REMOVE ".zip"
  !insertmacro EE_MENU_REMOVE ".zipx"
  !insertmacro EE_MENU_REMOVE ".7z"
  !insertmacro EE_MENU_REMOVE ".001"
  !insertmacro EE_MENU_REMOVE ".tar"
  !insertmacro EE_MENU_REMOVE ".gz"
  !insertmacro EE_MENU_REMOVE ".tgz"
  !insertmacro EE_MENU_REMOVE ".bz2"
  !insertmacro EE_MENU_REMOVE ".tbz"
  !insertmacro EE_MENU_REMOVE ".tbz2"
  !insertmacro EE_MENU_REMOVE ".xz"
  !insertmacro EE_MENU_REMOVE ".txz"
  !insertmacro EE_MENU_REMOVE ".zst"
  !insertmacro EE_MENU_REMOVE ".tzst"
  !insertmacro EE_MENU_REMOVE ".lzma"
  !insertmacro EE_MENU_REMOVE ".z"
  !insertmacro EE_MENU_REMOVE ".arj"
  !insertmacro EE_MENU_REMOVE ".lzh"
  !insertmacro EE_MENU_REMOVE ".lha"
  !insertmacro EE_MENU_REMOVE ".cpio"
  !insertmacro EE_MENU_REMOVE ".cab"
  !insertmacro EE_MENU_REMOVE ".wim"
  DeleteRegKey HKCU "Software\Classes\SystemFileAssociations\.iso\shell\EnhancedExtractISO"
!macroend
