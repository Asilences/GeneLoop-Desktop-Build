; Use the normal NSIS install section after a single branded setup page.
!macro customInstallMode
  !ifndef BUILD_UNINSTALLER
    ${If} $hasPerMachineInstallation != "1"
      StrCpy $isForceCurrentInstall "1"
    ${EndIf}
  !endif
!macroend

!macro customPageAfterChangeDir
  !insertmacro MUI_PAGE_INIT
  !insertmacro MUI_PAGE_FUNCTION_FULLWINDOW
  Page custom geneLoopSetupPage

  Var GeneLoopOptions
  Var GeneLoopPath
  Var GeneLoopBrowse
  Var GeneLoopExpanded
  Var GeneLoopHeroBitmap
  Var GeneLoopTitleFont

  Function geneLoopSetupPage
    ${If} ${isUpdated}
      Abort
    ${EndIf}
    nsDialogs::Create 1044
    Pop $0
    ${If} $0 == error
      Abort
    ${EndIf}
    SetCtlColors $0 "202638" "FFFFFF"
    InitPluginsDir
    File /oname=$PLUGINSDIR\geneLoop-setup.bmp "${BUILD_RESOURCES_DIR}\installerHero.bmp"
    ${NSD_CreateBitmap} 0u 0u 100% 76u ""
    Pop $1
    ${NSD_SetImage} $1 "$PLUGINSDIR\geneLoop-setup.bmp" $GeneLoopHeroBitmap

    ${NSD_CreateLabel} 0u 79u 100% 22u "GeneLoop Desktop"
    Pop $1
    ${NSD_AddStyle} $1 ${SS_CENTER}
    SetCtlColors $1 "202638" "FFFFFF"
    CreateFont $GeneLoopTitleFont "Segoe UI" "16" "600"
    SendMessage $1 ${WM_SETFONT} $GeneLoopTitleFont 1
    ${If} $LANGUAGE == 2052
      StrCpy $2 "让研究，向前一步。"
      StrCpy $3 "立即安装"
      StrCpy $4 "自定义安装位置"
      StrCpy $5 "更改"
    ${Else}
      StrCpy $2 "Move research forward."
      StrCpy $3 "Install now"
      StrCpy $4 "Customize install location"
      StrCpy $5 "Browse"
    ${EndIf}
    ${NSD_CreateLabel} 0u 104u 100% 13u "$2"
    Pop $1
    ${NSD_AddStyle} $1 ${SS_CENTER}
    SetCtlColors $1 "616B80" "FFFFFF"
    ${NSD_CreateButton} 32% 122u 36% 25u "$3"
    Pop $1
    ${NSD_AddStyle} $1 ${BS_DEFPUSHBUTTON}
    ${NSD_OnClick} $1 geneLoopStartInstall
    ${NSD_CreateCheckbox} 8% 151u 84% 13u "$4"
    Pop $GeneLoopOptions
    SetCtlColors $GeneLoopOptions "45546C" "FFFFFF"
    ${NSD_OnClick} $GeneLoopOptions geneLoopToggleLocation
    ${NSD_CreateLabel} 8% 171u 68% 19u "$INSTDIR"
    Pop $GeneLoopPath
    SetCtlColors $GeneLoopPath "45546C" "FFFFFF"
    ${NSD_CreateButton} 78% 167u 14% 20u "$5"
    Pop $GeneLoopBrowse
    ${NSD_OnClick} $GeneLoopBrowse geneLoopBrowseLocation
    ShowWindow $GeneLoopPath ${SW_HIDE}
    ShowWindow $GeneLoopBrowse ${SW_HIDE}
    Call muiPageLoadFullWindow
    GetDlgItem $0 $HWNDPARENT 1
    ShowWindow $0 ${SW_HIDE}
    nsDialogs::Show
    GetDlgItem $0 $HWNDPARENT 1
    ShowWindow $0 ${SW_SHOW}
    Call muiPageUnloadFullWindow
    ${NSD_FreeImage} $GeneLoopHeroBitmap
    System::Call 'gdi32::DeleteObject(p $GeneLoopTitleFont)'
  FunctionEnd

  Function geneLoopToggleLocation
    Pop $0
    ${NSD_GetState} $GeneLoopOptions $GeneLoopExpanded
    ${If} $GeneLoopExpanded == ${BST_CHECKED}
      ShowWindow $GeneLoopPath ${SW_SHOW}
      ShowWindow $GeneLoopBrowse ${SW_SHOW}
    ${Else}
      ShowWindow $GeneLoopPath ${SW_HIDE}
      ShowWindow $GeneLoopBrowse ${SW_HIDE}
    ${EndIf}
  FunctionEnd

  Function geneLoopBrowseLocation
    Pop $0
    ${If} $LANGUAGE == 2052
      StrCpy $1 "选择 GeneLoop Desktop 的安装位置"
    ${Else}
      StrCpy $1 "Choose where to install GeneLoop Desktop"
    ${EndIf}
    nsDialogs::SelectFolderDialog "$1" "$INSTDIR"
    Pop $0
    ${If} $0 == error
      Return
    ${EndIf}
    ${GetFileName} "$0" $1
    ${If} $1 != "${APP_FILENAME}"
      StrCpy $0 "$0\${APP_FILENAME}"
    ${EndIf}
    GetFullPathName $INSTDIR "$0"
    ${NSD_SetText} $GeneLoopPath "$INSTDIR"
  FunctionEnd

  Function geneLoopStartInstall
    Pop $0
    SendMessage $HWNDPARENT ${WM_COMMAND} 1 0
  FunctionEnd
!macroend

; electron-builder 使用 x86 Unicode NSIS。PROCESSENTRY32W 为 556 字节，
; szExeFile 位于偏移 36。只读系统快照，不打开其他程序的进程句柄。
!macro geneLoopFindProcess RESULT
  Push $0
  Push $1
  Push $2
  Push $3
  Push $4
  Push $5
  StrCpy ${RESULT} 1
  System::Call 'kernel32::CreateToolhelp32Snapshot(i 2, i 0) p .r0'
  ${If} $0 != -1
    System::Alloc 556
    Pop $1
    ${If} $1 P<> 0
      System::Call '*$1(i 556)'
      IntOp $4 $1 + 36
      System::Call 'kernel32::Process32FirstW(p r0, p r1) i .r2 ?e'
      Pop $3
      ${While} $2 != 0
        System::Call '*$4(&w260 .r5)'
        ${If} $5 == "${APP_EXECUTABLE_FILENAME}"
          StrCpy ${RESULT} 0
          ${ExitWhile}
        ${EndIf}
        System::Call 'kernel32::Process32NextW(p r0, p r1) i .r2 ?e'
        Pop $3
      ${EndWhile}
      ${If} $2 == 0
      ${AndIf} $3 == 18 ; ERROR_NO_MORE_FILES
        StrCpy ${RESULT} 603
      ${EndIf}
      System::Free $1
    ${EndIf}
    System::Call 'kernel32::CloseHandle(p r0)'
  ${EndIf}
  Pop $5
  Pop $4
  Pop $3
  Pop $2
  Pop $1
  Pop $0
!macroend

!macro customCheckAppRunning
  Push $R0
  ${Do}
    !insertmacro geneLoopFindProcess $R0
    ${If} $R0 == 603
      ${ExitDo}
    ${ElseIf} $R0 == 0
      ${If} ${Silent}
        SetErrorLevel 1618
        Quit
      ${EndIf}
      MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION \
        "检测到 ${PRODUCT_NAME} 进程仍在运行。请从托盘菜单选择退出，再点击重试。安装程序不会强制结束其他程序。" \
        /SD IDCANCEL IDRETRY +3
      SetErrorLevel 1618
      Quit
    ${Else}
      MessageBox MB_OK|MB_ICONSTOP \
        "无法读取 Windows 进程列表，安装已停止。请关闭安装程序后重试。" /SD IDOK
      SetErrorLevel 1
      Quit
    ${EndIf}
  ${Loop}
  Pop $R0
!macroend
