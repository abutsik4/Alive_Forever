!include "MUI2.nsh"
!include "LogicLib.nsh"

!define APP_NAME "Alive Forever"
!define APP_EXE "AliveForever.exe"
!define APP_DIRNAME "AliveForever"
!define COMPANY_NAME "abutsik4"
!define VERSION "1.0.0"
!define INSTALL_ROOT "$LOCALAPPDATA\Programs\${APP_DIRNAME}"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_DIRNAME}"

Name "${APP_NAME}"
OutFile "..\dist\AliveForever-Setup.exe"
InstallDir "${INSTALL_ROOT}"
RequestExecutionLevel user
Unicode True

!define MUI_ICON "..\icon.ico"
!define MUI_UNICON "..\icon.ico"

!define TASK_NAME "${APP_NAME}"

; Offer to launch straight after install, so the app is running before the
; user has to think about it.
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "Start ${APP_NAME} now"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "${APP_NAME} (required)" SEC_CORE
    SectionIn RO
    SetOutPath "$INSTDIR"
    File /r "..\dist\AliveForever\*"

    WriteUninstaller "$INSTDIR\Uninstall.exe"
    CreateDirectory "$SMPROGRAMS\${APP_NAME}"
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
    CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"

    WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayName" "${APP_NAME}"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "Publisher" "${COMPANY_NAME}"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayVersion" "${VERSION}"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "UninstallString" "$INSTDIR\Uninstall.exe"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\${APP_EXE}"
    WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoModify" 1
    WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoRepair" 1
SectionEnd

Section "Start automatically at sign-in" SEC_STARTUP
    ; Delegated to the app rather than calling schtasks here, because
    ; `schtasks /Create /SC ONLOGON` requires elevation and this installer runs
    ; as the user. The app registers a per-user logon task from an XML
    ; definition, which does not, and falls back to the Run key by itself.
    nsExec::ExecToStack '"$INSTDIR\${APP_EXE}" --register-startup'
    Pop $0
    Pop $1
    ${If} $0 != 0
        ; Even the app's fallback failed (locked-down machine, policy); write
        ; the Run key directly so the user still gets auto-start.
        WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${APP_NAME}" '"$INSTDIR\${APP_EXE}"'
    ${EndIf}
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_CORE} "The ${APP_NAME} application and its shortcuts."
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_STARTUP} "Run ${APP_NAME} automatically when you sign in to Windows. Recommended - otherwise you have to start it by hand every time."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Section "Uninstall"
    ; Ask the running copy to quit so its files are not locked below.
    nsExec::ExecToStack '"$SYSDIR\taskkill.exe" /IM "${APP_EXE}" /F'
    Pop $0
    Pop $1

    ; Clear auto-start before the exe is deleted, since the app removes its own
    ; registration. The schtasks and Run key lines below are belt and braces for
    ; an install that used the direct fallback.
    nsExec::ExecToStack '"$INSTDIR\${APP_EXE}" --unregister-startup'
    Pop $0
    Pop $1
    nsExec::ExecToStack '"$SYSDIR\schtasks.exe" /Delete /TN "${TASK_NAME}" /F'
    Pop $0
    Pop $1
    DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${APP_NAME}"

    Delete "$DESKTOP\${APP_NAME}.lnk"
    Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
    RMDir "$SMPROGRAMS\${APP_NAME}"

    Delete "$INSTDIR\Uninstall.exe"
    RMDir /r "$INSTDIR"

    DeleteRegKey HKCU "${UNINSTALL_KEY}"
SectionEnd