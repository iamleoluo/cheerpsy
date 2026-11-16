"""Google 日曆同步工作者：獨立 process，讀 outbox 推到 Google。

執行：`python -m app.gcal_worker`（docker-compose 的 worker 服務就是這個）。
預約 API 與這個 process 只透過資料庫的 gcal_outbox 溝通；工作者停了預約照常運作，只是 Google 暫時不更新，
重新啟動後會接著處理。可同時跑多個（領取用 FOR UPDATE SKIP LOCKED）。
"""

import logging
import signal
import threading

from app.services import gcal_push

IDLE_SECONDS = 5  # 沒事做時多久看一次 outbox
BUSY_SECONDS = 1  # 剛處理完一批，稍微喘口氣再看

logger = logging.getLogger("cheerpsy.gcal")
_stop = threading.Event()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: _stop.set())
    logger.info("gcal worker started")
    while not _stop.is_set():
        n = gcal_push.run_once()
        _stop.wait(BUSY_SECONDS if n else IDLE_SECONDS)
    logger.info("gcal worker stopped")


if __name__ == "__main__":
    main()
