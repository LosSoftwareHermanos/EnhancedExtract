; Add a collapsible "EnhancedExtract" submenu for .rar without changing the user's
; default archive application. Registered under SystemFileAssociations so it only
; appears on .rar files and needs no AppliesTo filter.
!macro NSIS_HOOK_POSTINSTALL
  DeleteRegKey HKCU "Software\Classes\*\shell\EnhancedExtract"
  DeleteRegKey HKCU "Software\Classes\*\shell\EnhancedExtractFree"
  DeleteRegKey HKCU "Software\Classes\SystemFileAssociations\.rar\shell\EnhancedExtractFree"
  DeleteRegKey HKCU "Software\Classes\SystemFileAssociations\.rar\shell\EnhancedExtract1"
  DeleteRegKey HKCU "Software\Classes\SystemFileAssociations\.rar\shell\EnhancedExtract2"
  DeleteRegKey HKCU "Software\Classes\SystemFileAssociations\.rar\shell\EnhancedExtract3"
  DeleteRegKey HKCU "Software\Classes\SystemFileAssociations\.rar\shell\EnhancedExtract"
  WriteRegStr HKCU "Software\Classes\SystemFileAssociations\.rar\shell\EnhancedExtract" "MUIVerb" "EnhancedExtract"
  WriteRegStr HKCU "Software\Classes\SystemFileAssociations\.rar\shell\EnhancedExtract" "Icon" '"$INSTDIR\${MAINBINARYNAME}.exe",0'
  WriteRegStr HKCU "Software\Classes\SystemFileAssociations\.rar\shell\EnhancedExtract" "SubCommands" ""
  WriteRegStr HKCU "Software\Classes\SystemFileAssociations\.rar\shell\EnhancedExtract\shell\1extract" "" "Extract with EnhancedExtract"
  WriteRegStr HKCU "Software\Classes\SystemFileAssociations\.rar\shell\EnhancedExtract\shell\1extract" "Icon" '"$INSTDIR\${MAINBINARYNAME}.exe",0'
  WriteRegStr HKCU "Software\Classes\SystemFileAssociations\.rar\shell\EnhancedExtract\shell\1extract\command" "" '"$INSTDIR\${MAINBINARYNAME}.exe" --shell-extract "%1"'
  WriteRegStr HKCU "Software\Classes\SystemFileAssociations\.rar\shell\EnhancedExtract\shell\2free" "" "Extract and free space (delete parts)..."
  WriteRegStr HKCU "Software\Classes\SystemFileAssociations\.rar\shell\EnhancedExtract\shell\2free" "Icon" '"$INSTDIR\${MAINBINARYNAME}.exe",0'
  WriteRegStr HKCU "Software\Classes\SystemFileAssociations\.rar\shell\EnhancedExtract\shell\2free\command" "" '"$INSTDIR\${MAINBINARYNAME}.exe" --shell-extract-delete "%1"'
  WriteRegStr HKCU "Software\Classes\SystemFileAssociations\.rar\shell\EnhancedExtract\shell\3open" "" "Open EnhancedExtract dashboard"
  WriteRegStr HKCU "Software\Classes\SystemFileAssociations\.rar\shell\EnhancedExtract\shell\3open" "Icon" '"$INSTDIR\${MAINBINARYNAME}.exe",0'
  WriteRegStr HKCU "Software\Classes\SystemFileAssociations\.rar\shell\EnhancedExtract\shell\3open\command" "" '"$INSTDIR\${MAINBINARYNAME}.exe"'
  ; Shortcuts launch the dashboard as administrator (needed for ISO install). The
  ; right-click extract entries run the exe directly and stay unelevated.
  nsExec::Exec `powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "foreach($$p in \"$SMPROGRAMS\${PRODUCTNAME}.lnk\",\"$DESKTOP\${PRODUCTNAME}.lnk\"){ if(Test-Path $$p){ $$b=[IO.File]::ReadAllBytes($$p); $$b[0x15]=$$b[0x15] -bor 0x20; [IO.File]::WriteAllBytes($$p,$$b) } }"`
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  DeleteRegKey HKCU "Software\Classes\*\shell\EnhancedExtract"
  DeleteRegKey HKCU "Software\Classes\*\shell\EnhancedExtractFree"
  DeleteRegKey HKCU "Software\Classes\SystemFileAssociations\.rar\shell\EnhancedExtract"
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
!macroend
