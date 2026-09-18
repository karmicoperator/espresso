; espresso for Windows: a per-user installer, so no administrator password is asked for.
; The app goes to %LOCALAPPDATA%\Programs\espresso, the shortcuts to this person's Start menu
; and desktop, and its entry in Settings, Apps to HKCU. Built by scripts/package-windows.sh:
;
;   makensis -DVERSION=<sha> -DPAYLOAD=<staged source> -DOUTFILE=<exe> windows/installer.nsi
;
; Unsigned: Windows warns once before running it ("More info", "Run anyway").

Unicode true
SetCompressor /SOLID lzma
!include "MUI2.nsh"
!include "LogicLib.nsh"

Name "espresso"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\Programs\espresso"
RequestExecutionLevel user
BrandingText "espresso ${VERSION}"
ShowInstDetails nevershow
ShowUninstDetails nevershow

!define PS "$WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe"
!define RUNARGS '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "$INSTDIR\windows\espresso.ps1"'
!define HELPER '"${PS}" -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\windows\installer-helper.ps1"'
!define UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\espresso"

!define MUI_ICON "${PAYLOAD}\windows\espresso.ico"
!define MUI_UNICON "${PAYLOAD}\windows\espresso.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP "${PAYLOAD}\windows\installer-side.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "${PAYLOAD}\windows\installer-side.bmp"
!define MUI_FINISHPAGE_TITLE "espresso is installed"
!define MUI_FINISHPAGE_TEXT "The first start takes about five minutes while espresso downloads what it needs and builds itself. A small window shows how far it is, and your browser opens by itself when espresso is ready.$\r$\n$\r$\nAfter that, open espresso from the Start menu or the desktop. While it runs, its cup sits in the notification area by the clock: click it to open espresso, right-click it to quit."
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Start espresso now"
!define MUI_FINISHPAGE_RUN_FUNCTION StartEspresso

!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

; Through the shortcut, so espresso starts the way it always will: console hidden.
Function StartEspresso
  ExecShell "open" "$SMPROGRAMS\espresso.lnk"
FunctionEnd

Section "espresso"
  ; Over an earlier version: stop it, then clear its code but keep the papers, the settings
  ; and the installed packages, so an update is quick and loses nothing.
  ${If} ${FileExists} "$INSTDIR\windows\installer-helper.ps1"
    DetailPrint "Stopping the running espresso"
    nsExec::Exec '${HELPER} -Action stop -InstallDir "$INSTDIR"'
    Pop $0
    nsExec::Exec '${HELPER} -Action upgrade-clean -InstallDir "$INSTDIR"'
    Pop $0
  ${EndIf}

  SetOutPath "$INSTDIR"
  File /r "${PAYLOAD}\*"
  WriteUninstaller "$INSTDIR\uninstall.exe"

  CreateShortcut "$SMPROGRAMS\espresso.lnk" "${PS}" '${RUNARGS}' "$INSTDIR\windows\espresso.ico" 0 SW_SHOWMINIMIZED "" "Five-minute reads of medical papers"
  CreateShortcut "$DESKTOP\espresso.lnk" "${PS}" '${RUNARGS}' "$INSTDIR\windows\espresso.ico" 0 SW_SHOWMINIMIZED "" "Five-minute reads of medical papers"

  WriteRegStr HKCU "${UNINSTKEY}" "DisplayName" "espresso"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINSTKEY}" "Publisher" "espresso"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayIcon" "$INSTDIR\windows\espresso.ico"
  WriteRegStr HKCU "${UNINSTKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINSTKEY}" "URLInfoAbout" "https://github.com/karmicoperator/espresso"
  WriteRegStr HKCU "${UNINSTKEY}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKCU "${UNINSTKEY}" "QuietUninstallString" '"$INSTDIR\uninstall.exe" /S'
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  nsExec::Exec '${HELPER} -Action stop -InstallDir "$INSTDIR"'
  Pop $0
  Delete "$SMPROGRAMS\espresso.lnk"
  Delete "$DESKTOP\espresso.lnk"
  DeleteRegKey HKCU "${UNINSTKEY}"

  ; A silent uninstall keeps the papers: losing them should take a click.
  MessageBox MB_YESNO|MB_ICONQUESTION "Also delete the papers you built and your settings?$\r$\n$\r$\nChoose No to keep them for when you install espresso again." /SD IDNO IDYES purge
  nsExec::Exec '${HELPER} -Action keep-data -InstallDir "$INSTDIR"'
  Pop $0
  Goto tools
  purge:
  RMDir /r "$INSTDIR"
  tools:
  ; Downloaded Python, Node.js, caches and logs.
  RMDir /r "$LOCALAPPDATA\espresso"
SectionEnd
