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

!macro EE_MENU_REMOVE EXT
  DeleteRegKey HKCU "Software\Classes\SystemFileAssociations\${EXT}\shell\EnhancedExtract"
!macroend

!macro NSIS_HOOK_POSTINSTALL
  DeleteRegKey HKCU "Software\Classes\*\shell\EnhancedExtract"
  DeleteRegKey HKCU "Software\Classes\*\shell\EnhancedExtractFree"
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
  ; Shortcuts launch the dashboard as administrator (needed for ISO install). The
  ; right-click extract entries run the exe directly and stay unelevated.
  nsExec::Exec `powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "foreach($$p in \"$SMPROGRAMS\${PRODUCTNAME}.lnk\",\"$DESKTOP\${PRODUCTNAME}.lnk\"){ if(Test-Path $$p){ $$b=[IO.File]::ReadAllBytes($$p); $$b[0x15]=$$b[0x15] -bor 0x20; [IO.File]::WriteAllBytes($$p,$$b) } }"`
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  DeleteRegKey HKCU "Software\Classes\*\shell\EnhancedExtract"
  DeleteRegKey HKCU "Software\Classes\*\shell\EnhancedExtractFree"
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
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
!macroend
