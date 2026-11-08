"""每台Worker维护本地复盘档案，避免集中Beat任务只清理到其中一台机器。"""

from celery import signals

from tender.core.di import create_analysis_archive


def _start(**kwargs) -> None:
    create_analysis_archive().start()


def _stop(**kwargs) -> None:
    create_analysis_archive().close()


def install_analysis_maintenance() -> None:
    for signal, callback, name in (
        (signals.worker_init, _start, "start"),
        (signals.worker_process_init, _start, "child"),
        (signals.worker_shutdown, _stop, "stop"),
        (signals.worker_process_shutdown, _stop, "child_stop"),
    ):
        signal.connect(callback, weak=False, dispatch_uid="tender.analysis.archive." + name)
