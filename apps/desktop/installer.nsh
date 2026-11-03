; 只检查应用的准确进程名，不用安装目录前缀匹配或结束同目录其他程序。
; nsProcess 由 electron-builder 的 NSIS 插件提供：0=找到，603=没有找到。
!macro customCheckAppRunning
  Push $R0
  ${Do}
    nsProcess::_FindProcess "${APP_EXECUTABLE_FILENAME}"
    Pop $R0
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
        "无法可靠检查 ${PRODUCT_NAME} 的运行状态（错误码 $R0）。请关闭安装程序后重试。" /SD IDOK
      SetErrorLevel 1
      Quit
    ${EndIf}
  ${Loop}
  Pop $R0
!macroend
