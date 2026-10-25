; Farmandari App - NSIS Installer Script (onedir build)
; Build: makensis farmandari.nsi

Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"

!define APP_NAME "سامانه فرمانداری"
!define APP_EXE "FarmandariApp.exe"
!define APP_REGKEY "FarmandariApp"
!define APP_TITLE "برنامه هماهنگی امورات فرمانداری"
!define APP_VERSION "1.2.0"

Name "${APP_NAME}"
OutFile "Output\FarmandariSetup_${APP_VERSION}.exe"
InstallDir "$PROGRAMFILES64\Farmandari"
InstallDirRegKey HKLM "Software\${APP_REGKEY}" ""
RequestExecutionLevel admin
Var StartMenuFolder
ShowInstDetails show
ShowUninstDetails show
XPStyle on

!define MUI_ICON "resources\icon.ico"
!define MUI_UNICON "resources\icon.ico"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_STARTMENU Application $StartMenuFolder
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_WELCOME
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

!insertmacro MUI_LANGUAGE "Farsi"
!insertmacro MUI_LANGUAGE "English"

Section "Main" SEC_MAIN
    SetOutPath "$INSTDIR"

    File /r "dist\FarmandariApp\*.*"
    File "LICENSE.txt"
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    !insertmacro MUI_STARTMENU_WRITE_BEGIN Application
        CreateDirectory "$SMPROGRAMS\${APP_NAME}"
        CreateShortCut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
        CreateShortCut "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
    !insertmacro MUI_STARTMENU_WRITE_END

    CreateShortCut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"

    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_REGKEY}" "DisplayName" "${APP_NAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_REGKEY}" "DisplayVersion" "${APP_VERSION}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_REGKEY}" "Publisher" "Farmandari"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_REGKEY}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_REGKEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_REGKEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_REGKEY}" "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_REGKEY}" "NoRepair" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_REGKEY}" "EstimatedSize" 200000
    WriteRegStr HKLM "Software\${APP_REGKEY}" "" "$INSTDIR"
SectionEnd

Section "Uninstall"
    Delete "$DESKTOP\${APP_NAME}.lnk"
    RMDir /r "$SMPROGRAMS\${APP_NAME}"

    RMDir /r "$INSTDIR"

    ; داده‌های کاربر در %LOCALAPPDATA%\Farmandari نگه داشته می‌شوند
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_REGKEY}"
    DeleteRegKey HKLM "Software\${APP_REGKEY}"
SectionEnd

Function .onInit
    ; نصب بی‌صدا (/S) نباید منتظر تأیید تعاملی بماند
    IfSilent done
    ReadRegStr $0 HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_REGKEY}" "UninstallString"
    StrCmp $0 "" done
    MessageBox MB_YESNO|MB_ICONQUESTION "نسخهٔ قبلی نصب شده است. ارتقا داده شود؟" IDYES done
    Abort
    done:
FunctionEnd

Function un.onInit
    FindWindow $0 "" "${APP_TITLE}"
    StrCmp $0 0 +3
        MessageBox MB_OK|MB_ICONEXCLAMATION "برنامه در حال اجراست. ابتدا آن را ببندید."
        Abort
FunctionEnd
