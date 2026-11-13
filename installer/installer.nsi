; Vino's Office setup
;
; Built by ../build.py, which passes:
;   VERSION        Vino's Office version, e.g. 1.0.0
;   LO_VERSION     bundled LibreOffice version, e.g. 26.8.3
;   LO_MSI         path to the LibreOffice .msi
;   LO_PRODUCTCODE MSI ProductCode (for uninstall)
;   OUTFILE        setup .exe to write
;
; On a PC without LibreOffice: installs the bundled LibreOffice into the chosen folder (hidden from
; Apps & Features, so only "Vino's Office" appears), then brands it.
; On a PC that already has LibreOffice: brands that installation and leaves LibreOffice in place.
; Uninstalling reverses exactly what was done.

Unicode true
ManifestDPIAware true
!include MUI2.nsh
!include LogicLib.nsh
!include x64.nsh
!include FileFunc.nsh

!define APP "Vino's Office"
!define REGKEY "Software\VinosOffice"
!define UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\VinosOffice"
!define BRAND "..\brand\out"
!define BUILD "..\build"

Name "${APP}"
OutFile "${OUTFILE}"
InstallDir "$PROGRAMFILES64\Vinos Office"
RequestExecutionLevel admin
SetCompressor /SOLID lzma
BrandingText "${APP} ${VERSION}"
VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${APP}"
VIAddVersionKey "FileDescription" "${APP} Setup"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "Built on LibreOffice (MPL-2.0)"

!define MUI_ICON "${BRAND}\vinos-office.ico"
!define MUI_UNICON "${BRAND}\vinos-office.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP "${BRAND}\installer-side.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "${BRAND}\installer-side.bmp"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_RIGHT
!define MUI_HEADERIMAGE_BITMAP "${BRAND}\installer-header.bmp"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Welcome to ${APP}"
!define MUI_WELCOMEPAGE_TEXT "This will install ${APP} ${VERSION}: spreadsheets, documents and presentations, with Sheets Home (Ctrl+Shift+H) for workbooks with many sheets.$\r$\n$\r$\nSetup takes a few minutes. Please close any open documents before continuing."
!define MUI_FINISHPAGE_RUN "$LOProg\scalc.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Open ${APP} Calc"

Var LOProg       ; ...\program folder of the office suite
Var Existing     ; 0 = fresh install, 1 = someone else's LibreOffice is here, 2 = updating our own install

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "notice.txt"
!define MUI_PAGE_CUSTOMFUNCTION_PRE SkipDirIfExisting
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "${APP} needs 64-bit Windows."
    Abort
  ${EndIf}
  SetRegView 64
  SetShellVarContext all
  StrCpy $Existing 0
  ReadRegStr $0 HKLM "${REGKEY}" "SuiteByVino"
  ReadRegStr $1 HKLM "SOFTWARE\LibreOffice\UNO\InstallPath" ""
  ${If} $1 != ""
  ${AndIf} ${FileExists} "$1\soffice.exe"
    StrCpy $LOProg $1
    ${If} $0 == "1"
      StrCpy $Existing 2
      ReadRegStr $2 HKLM "${REGKEY}" "InstallDir"
      ${If} $2 != ""
        StrCpy $INSTDIR $2
      ${EndIf}
    ${Else}
      StrCpy $Existing 1
    ${EndIf}
  ${EndIf}
FunctionEnd

Function SkipDirIfExisting
  ${If} $Existing != 0
    Abort
  ${EndIf}
FunctionEnd

; Back up an original file once, so uninstall can put it back
!macro Backup FILE
  ${IfNot} ${FileExists} "${FILE}.vinos-orig"
  ${AndIf} ${FileExists} "${FILE}"
    CopyFiles /SILENT "${FILE}" "${FILE}.vinos-orig"
  ${EndIf}
!macroend

Section "Install"
  SetOutPath "$INSTDIR\branding"
  File "${BRAND}\vinos-office.ico"

  ${If} $Existing == 0
    DetailPrint "Installing the office suite (this takes a few minutes)..."
    SetOutPath "$PLUGINSDIR"
    File /oname=suite.msi "${LO_MSI}"
    ExecWait 'msiexec.exe /i "$PLUGINSDIR\suite.msi" /qn /norestart ALLUSERS=1 INSTALLLOCATION="$INSTDIR" CREATEDESKTOPLINK=0 REGISTER_NO_MSO_TYPES=1 ISCHECKFORPRODUCTUPDATES=0 QUICKSTART=0 REMOVE=gm_o_Onlineupdate ARPSYSTEMCOMPONENT=1 RebootYesNo=No /l*v "$TEMP\VinosOffice-suite-install.log"' $0
    Delete "$PLUGINSDIR\suite.msi"
    ${If} $0 != 0
    ${AndIf} $0 != 3010
      MessageBox MB_ICONSTOP "The office suite could not be installed (error $0).$\r$\nDetails: $TEMP\VinosOffice-suite-install.log"
      Abort
    ${EndIf}
    StrCpy $LOProg "$INSTDIR\program"
    WriteRegStr HKLM "${REGKEY}" "SuiteByVino" "1"
    WriteRegStr HKLM "${REGKEY}" "SuiteProductCode" "${LO_PRODUCTCODE}"
    RMDir /r "$SMPROGRAMS\LibreOffice ${LO_VERSION}"
    RMDir /r "$SMPROGRAMS\LibreOffice 26.8"
  ${ElseIf} $Existing == 1
    DetailPrint "LibreOffice found in $LOProg - applying ${APP} to it."
    WriteRegStr HKLM "${REGKEY}" "SuiteByVino" "0"
  ${Else}
    DetailPrint "Updating ${APP} in $LOProg..."
  ${EndIf}
  WriteRegStr HKLM "${REGKEY}" "ProgramDir" "$LOProg"
  WriteRegStr HKLM "${REGKEY}" "InstallDir" "$INSTDIR"

  DetailPrint "Applying ${APP} branding..."
  !insertmacro Backup "$LOProg\intro.png"
  !insertmacro Backup "$LOProg\intro-highres.png"
  !insertmacro Backup "$LOProg\soffice.ini"
  !insertmacro Backup "$LOProg\shell\logo.svg"
  !insertmacro Backup "$LOProg\shell\logo_inverted.svg"
  !insertmacro Backup "$LOProg\shell\logo-sc.svg"
  !insertmacro Backup "$LOProg\shell\logo-sc_inverted.svg"
  !insertmacro Backup "$LOProg\shell\about.svg"
  SetOutPath "$LOProg"
  File "${BRAND}\program\intro.png"
  File "${BRAND}\program\intro-highres.png"
  SetOutPath "$LOProg\shell"
  File "${BRAND}\program\shell\*.svg"
  WriteINIStr "$LOProg\soffice.ini" "Bootstrap" "ProgressBarColor" "64,196,214"
  WriteINIStr "$LOProg\soffice.ini" "Bootstrap" "ProgressFrameColor" "40,60,80"
  WriteINIStr "$LOProg\soffice.ini" "Bootstrap" "ProgressPosition" "180,140"
  WriteINIStr "$LOProg\soffice.ini" "Bootstrap" "ProgressSize" "260,6"
  WriteINIStr "$LOProg\soffice.ini" "Bootstrap" "ProgressTextBaseline" "170"
  WriteINIStr "$LOProg\soffice.ini" "Bootstrap" "ProgressTextColor" "150,175,196"

  DetailPrint "Adding Sheets Home and ${APP} settings..."
  SetOutPath "$INSTDIR\branding"
  File "${BUILD}\VinosOfficeBranding.oxt"
  File "${BUILD}\SheetsHome.oxt"
  nsExec::ExecToLog '"$LOProg\unopkg.com" add --shared --force --suppress-license "$INSTDIR\branding\VinosOfficeBranding.oxt"'
  Pop $0
  nsExec::ExecToLog '"$LOProg\unopkg.com" add --shared --force --suppress-license "$INSTDIR\branding\SheetsHome.oxt"'
  Pop $1
  ${If} $0 != 0
  ${OrIf} $1 != 0
    MessageBox MB_ICONEXCLAMATION "The ${APP} add-ons could not be registered (codes $0 / $1). Close all ${APP} / LibreOffice windows and run Setup again."
  ${EndIf}

  DetailPrint "Creating shortcuts..."
  CreateDirectory "$SMPROGRAMS\${APP}"
  CreateShortcut "$SMPROGRAMS\${APP}\${APP}.lnk" "$LOProg\soffice.exe" "" "$INSTDIR\branding\vinos-office.ico" 0
  CreateShortcut "$SMPROGRAMS\${APP}\${APP} Calc.lnk" "$LOProg\scalc.exe"
  CreateShortcut "$SMPROGRAMS\${APP}\${APP} Writer.lnk" "$LOProg\swriter.exe"
  CreateShortcut "$SMPROGRAMS\${APP}\${APP} Impress.lnk" "$LOProg\simpress.exe"
  CreateShortcut "$DESKTOP\${APP}.lnk" "$LOProg\soffice.exe" "" "$INSTDIR\branding\vinos-office.ico" 0
  CreateShortcut "$DESKTOP\${APP} Calc.lnk" "$LOProg\scalc.exe"

  WriteUninstaller "$INSTDIR\branding\Uninstall.exe"
  WriteRegStr HKLM "${UNINSTKEY}" "DisplayName" "${APP}"
  WriteRegStr HKLM "${UNINSTKEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "${UNINSTKEY}" "Publisher" "${APP}"
  WriteRegStr HKLM "${UNINSTKEY}" "DisplayIcon" "$INSTDIR\branding\vinos-office.ico"
  WriteRegStr HKLM "${UNINSTKEY}" "UninstallString" '"$INSTDIR\branding\Uninstall.exe"'
  WriteRegStr HKLM "${UNINSTKEY}" "InstallLocation" "$INSTDIR"
  WriteRegDWORD HKLM "${UNINSTKEY}" "NoModify" 1
  WriteRegDWORD HKLM "${UNINSTKEY}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  WriteRegDWORD HKLM "${UNINSTKEY}" "EstimatedSize" $0
SectionEnd

!macro Restore FILE
  ${If} ${FileExists} "${FILE}.vinos-orig"
    Delete "${FILE}"
    Rename "${FILE}.vinos-orig" "${FILE}"
  ${EndIf}
!macroend

Function un.onInit
  SetRegView 64
  SetShellVarContext all
FunctionEnd

Section "Uninstall"
  ReadRegStr $LOProg HKLM "${REGKEY}" "ProgramDir"
  ReadRegStr $2 HKLM "${REGKEY}" "SuiteByVino"
  ReadRegStr $3 HKLM "${REGKEY}" "SuiteProductCode"
  ReadRegStr $4 HKLM "${REGKEY}" "InstallDir"
  ${If} $4 == ""
    StrCpy $4 "$INSTDIR\.."
  ${EndIf}

  ${If} ${FileExists} "$LOProg\unopkg.com"
    DetailPrint "Removing add-ons..."
    nsExec::ExecToLog '"$LOProg\unopkg.com" remove --shared com.vinosoffice.branding'
    Pop $0
    nsExec::ExecToLog '"$LOProg\unopkg.com" remove --shared org.celllite.sheetshome'
    Pop $0
  ${EndIf}

  ${If} $2 == "1"
    DetailPrint "Removing the office suite (this takes a few minutes)..."
    ExecWait 'msiexec.exe /x $3 /qn /norestart' $0
  ${Else}
    DetailPrint "Restoring the original LibreOffice look..."
    !insertmacro Restore "$LOProg\intro.png"
    !insertmacro Restore "$LOProg\intro-highres.png"
    !insertmacro Restore "$LOProg\soffice.ini"
    !insertmacro Restore "$LOProg\shell\logo.svg"
    !insertmacro Restore "$LOProg\shell\logo_inverted.svg"
    !insertmacro Restore "$LOProg\shell\logo-sc.svg"
    !insertmacro Restore "$LOProg\shell\logo-sc_inverted.svg"
    !insertmacro Restore "$LOProg\shell\about.svg"
  ${EndIf}

  Delete "$SMPROGRAMS\${APP}\*.lnk"
  RMDir "$SMPROGRAMS\${APP}"
  Delete "$DESKTOP\${APP}.lnk"
  Delete "$DESKTOP\${APP} Calc.lnk"
  DeleteRegKey HKLM "${UNINSTKEY}"
  DeleteRegKey HKLM "${REGKEY}"
  RMDir /r "$4\branding"
  RMDir "$4"
SectionEnd
