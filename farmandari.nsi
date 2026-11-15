; Farmandari App - NSIS Installer Script (onedir build)
; Build x86: makensis /DAPP_ARCH=x86 /DAPP_SRC=dist\FarmandariApp-x86 farmandari.nsi
; Build x64: makensis /DAPP_ARCH=x64 /DAPP_SRC=dist\FarmandariApp-x64 farmandari.nsi
;
; The installer itself runs on Windows 7 SP1 and newer. Windows 7 also needs
; the Universal C Runtime (KB2999226) and KB2533623 because Python 3.8 links
; against them.

Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "WinVer.nsh"
!include "x64.nsh"

!ifndef APP_ARCH
    !define APP_ARCH "x64"
!endif
!ifndef APP_SRC
    !define APP_SRC "dist\FarmandariApp-${APP_ARCH}"
!endif
!ifndef OUTPUT_DIR
    !define OUTPUT_DIR "Output"
!endif

!define APP_NAME "سامانه فرمانداری"
!define APP_EXE "FarmandariApp-${APP_ARCH}.exe"
!define APP_REGKEY "FarmandariApp-${APP_ARCH}"
!define APP_TITLE "برنامه هماهنگی امورات فرمانداری"
; عنوان پنجرهٔ اصلی برنامه (settings.APP_NAME). پنجرهٔ ورود عنوان دیگری دارد،
; بنابراین هر دو برای تشخیص «برنامه در حال اجراست» بررسی می‌شوند.
!define APP_WINDOW_TITLE "سیستم مدیریت امور دفتری فرمانداری"
!define APP_VERSION "1.2.0"
!define SHORTCUT_NAME "${APP_NAME} (${APP_ARCH})"

Name "${APP_NAME} (${APP_ARCH})"
OutFile "${OUTPUT_DIR}\FarmandariSetup_${APP_VERSION}_${APP_ARCH}.exe"

!if "${APP_ARCH}" == "x64"
    InstallDir "$PROGRAMFILES64\Farmandari"
!else
    InstallDir "$PROGRAMFILES\Farmandari"
!endif
InstallDirRegKey HKLM "Software\${APP_REGKEY}" ""
RequestExecutionLevel admin
Var StartMenuFolder
ShowInstDetails show
ShowUninstDetails show
XPStyle on
SetCompressor /SOLID lzma

!define MUI_ICON "resources\icon.ico"
!define MUI_UNICON "resources\icon.ico"
!define MUI_ABORTWARNING

VIProductVersion "${APP_VERSION}.0"
VIAddVersionKey "ProductName" "${APP_NAME}"
VIAddVersionKey "CompanyName" "Farmandari"
VIAddVersionKey "FileDescription" "${APP_TITLE}"
VIAddVersionKey "FileVersion" "${APP_VERSION}"
VIAddVersionKey "ProductVersion" "${APP_VERSION}"
VIAddVersionKey "LegalCopyright" "Farmandari"

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

    File /r "${APP_SRC}\*.*"
    File "LICENSE.txt"
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    !insertmacro MUI_STARTMENU_WRITE_BEGIN Application
        CreateDirectory "$SMPROGRAMS\${SHORTCUT_NAME}"
        CreateShortCut "$SMPROGRAMS\${SHORTCUT_NAME}\${SHORTCUT_NAME}.lnk" "$INSTDIR\${APP_EXE}"
        CreateShortCut "$SMPROGRAMS\${SHORTCUT_NAME}\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
    !insertmacro MUI_STARTMENU_WRITE_END

    CreateShortCut "$DESKTOP\${SHORTCUT_NAME}.lnk" "$INSTDIR\${APP_EXE}"

    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_REGKEY}" "DisplayName" "${SHORTCUT_NAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_REGKEY}" "DisplayVersion" "${APP_VERSION}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_REGKEY}" "Publisher" "Farmandari"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_REGKEY}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_REGKEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_REGKEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_REGKEY}" "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_REGKEY}" "NoRepair" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_REGKEY}" "EstimatedSize" 250000
    WriteRegStr HKLM "Software\${APP_REGKEY}" "" "$INSTDIR"
SectionEnd

Section "Uninstall"
    Delete "$DESKTOP\${SHORTCUT_NAME}.lnk"
    RMDir /r "$SMPROGRAMS\${SHORTCUT_NAME}"

    RMDir /r "$INSTDIR"

    ; داده‌های کاربر در %LOCALAPPDATA%\Farmandari نگه داشته می‌شوند
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_REGKEY}"
    DeleteRegKey HKLM "Software\${APP_REGKEY}"
SectionEnd

Function .onInit
    ${IfNot} ${AtLeastWin7}
        MessageBox MB_OK|MB_ICONSTOP "این برنامه روی ویندوز ۷ یا جدیدتر نصب می‌شود."
        Abort
    ${EndIf}

    ${If} "${APP_ARCH}" == "x64"
        ${IfNot} ${RunningX64}
            MessageBox MB_OK|MB_ICONSTOP "این نسخه ۶۴ بیتی است. نسخه x86 را روی ویندوز ۳۲ بیتی نصب کنید."
            Abort
        ${EndIf}
    ${EndIf}

    ; Python 3.8 needs the Universal C Runtime on Windows 7. It is built into
    ; Windows 10/11, but Windows 7 SP1 needs KB2999226.
    ${IfNot} ${FileExists} "$SYSDIR\ucrtbase.dll"
        ${IfNot} ${FileExists} "$SYSDIR\api-ms-win-crt-runtime-l1-1-0.dll"
            MessageBox MB_OK|MB_ICONSTOP "ویندوز ۷ به به‌روزرسانی Universal C Runtime نیاز دارد.$\r$\nبه‌روزرسانی‌های KB2999226 و KB2533623 را نصب کنید و سپس دوباره تلاش کنید."
            Abort
        ${EndIf}
    ${EndIf}

    ; نصب بی‌صدا (/S) نباید منتظر تأیید تعاملی بماند
    IfSilent done
    ReadRegStr $0 HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_REGKEY}" "UninstallString"
    StrCmp $0 "" done
    MessageBox MB_YESNO|MB_ICONQUESTION "نسخهٔ ${APP_ARCH} قبلاً نصب شده است. ارتقا داده شود؟" IDYES done
    Abort
    done:
FunctionEnd

Function un.onInit
    FindWindow $0 "" "${APP_WINDOW_TITLE}"
    ${If} $0 == 0
        FindWindow $0 "" "${APP_TITLE}"
    ${EndIf}
    ${If} $0 != 0
        MessageBox MB_OK|MB_ICONEXCLAMATION "برنامه در حال اجراست. ابتدا آن را ببندید."
        Abort
    ${EndIf}
FunctionEnd
