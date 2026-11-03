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
