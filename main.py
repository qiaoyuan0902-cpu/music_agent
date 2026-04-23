import sys
from PyQt6.QtWidgets import QApplication


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 首次启动：弹出配置向导
    from ui.setup_wizard import is_configured, SetupWizard
    if not is_configured():
        wizard = SetupWizard()
        if wizard.exec() != SetupWizard.DialogCode.Accepted:
            sys.exit(0)
        # 向导完成后重新加载 .env
        from ui.setup_wizard import get_env_path
        from dotenv import load_dotenv
        load_dotenv(get_env_path(), override=True)

    from ui.qt_app import launch
    launch(app)


if __name__ == "__main__":
    main()
