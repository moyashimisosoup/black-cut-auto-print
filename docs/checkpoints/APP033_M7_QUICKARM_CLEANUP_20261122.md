# CHECKPOINT｜APP-033 M7 直接許可と元JPEGごみ箱移動

- APP-ID / work_id：APP-033 / APP033-M7-QUICKARM-CLEANUP-01
- 2026-11-22 JST
- Repo：`moyashimisosoup/black-cut-auto-print`（Public）
- branch：`feature/app033-m7-quickarm-cleanup-20261122`
- Draft PR：[PR #10](https://github.com/moyashimisosoup/black-cut-auto-print/pull/10)（base：PR #9のブランチ）
- v0.7.2-rc.1、main未統合。**Windows実紙・Canonの印刷完了通知は未検収。**

## 決定と実装

1. ユーザーの明示指示により、③「自動印刷を許可」を直接押すと、①試し刷りと②紙の結果確認を省略できるようにする。ただし試し刷り未確認の警告・明示同意を必須とし、実機検収済みとは区別する。以前の必須試し刷りルールは[ADR-010](../M7_QUICK_ARM_AND_CLEANUP.md)で正式改訂。
2. 監視開始前のJPEGは従来どおり自動印刷しない。起動時OFF、停止・プリンター変更・設定変更で許可失効。自動印刷の許可はディスクへ保存しない。
3. 「印刷完了を確認できた元JPEGを、ごみ箱へ移す」は**既定ON**、チェックOFFで保存可能。旧仕様の原稿保管ルールを[ADR-011](../M7_QUICK_ARM_AND_CLEANUP.md)で改訂。
4. 新規受信したJPEGが`SUBMITTED`になっただけでは削除しない。Windowsスプーラーの対象`JOB_STATUS_PRINTED`を確認したうえで、元画像のパス・安全な保存先・フィンガープリント一致を確認し、`Send2Trash`でごみ箱に移動する。ジョブが消えた・不明・エラー・差し替え・停止時は元画像を保持。
5. 手動試し刷り・古い履歴・受信フォルダ外・加工済みプレビュー・診断画像は削除しない。再起動後、古い印刷ジョブの確認を根拠に元画像を自動削除することもない。
6. 完了判断はスプーラーの報告であり、Canonの排紙センサーの実測ではない。印刷済みフラグを返さないWindowsキューの場合、画像は保守的に残る。
7. 未署名Windows評価用EXE・更新バッチを生成し、旧v0.7.1-rc.1の既知ハッシュからの更新を許す（ハッシュ不一致は拒否）。

## 検証

- [GitHub Actions #45008059073](https://github.com/moyashimisosoup/black-cut-auto-print/actions/runs/45008059073)：Linux単体**67 PASS**、仮想Tk GUI**8 PASS**（warning 1）。直接許可・旧画像無印刷・原本安全な処理を含む。
- [M2 pipeline CI #45008059074](https://github.com/moyashimisosoup/black-cut-auto-print/actions/runs/45008059074)：Linux/Windowsの合成試験成功。
- [更新バッチCI #45008059052](https://github.com/moyashimisosoup/black-cut-auto-print/actions/runs/45008059052)：Windowsの照合正常/不一致テスト成功。
- [GitHub Actions #45008059073](https://github.com/moyashimisosoup/black-cut-auto-print/actions/runs/45008059073)：Linux単体67件＋Xvfb仮想GUI8件PASS（警告1）、Windows単体67件PASS、未署名PyInstaller EXE生成とパッケージSHA検査PASS。
- [旧M4互換 CI #45008059084](https://github.com/moyashimisosoup/black-cut-auto-print/actions/runs/45008059084)：Linux/Windows合格。
- Windows Artifact `APP033-v0.7.2-rc.1-QuickArm-Recycle-Windows`（ID `14748970685`）を`APP033-v0.7.2-rc.1-QuickArm-Recycle-Windows.zip`として読戻し。サイズ`75,763,078` bytes、SHA-256 `c7b85d59b67d857a0dada9fca76dfefd8dabc1ad4197339e8b1032c79aa367cb`。
- ZIPは**7ファイルすべてCRC PASS**。EXE `76,295,623` bytes・MZヘッダー、SHA-256 `a0143c72f89309dbe4904dd1c397bace318fe4fb993d7043fa5fa205be1fed87`が`new_exe_sha256.txt`と一致、`VERSION.txt`は`v0.7.2-rc.1`。
- **実機のCanon MF244dwの排紙・WindowsのPRINTEDフラグ・ごみ箱移動は未確認**。

## 残工程

- [ ] Windows実機で直接③→④→本体新規スキャン→Canonで1枚排紙を確認
- [ ] Windowsの`JOB_STATUS_PRINTED`を実際のMF240 Seriesキューから取得でき、ごみ箱へ移動するか、確認不可のため保持するか観察
- [ ] JPG上書き・連続3件・停止/再起動・キューエラー時の保持を実機で検収
- [ ] main統合・正式版配布

次の1操作：v0.7.2 RC評価EXEを起動し、チェックONと③ボタンからの明示許可を確認。その後、④監視開始→新規スキャンで排紙とごみ箱結果を確認。Canon実紙が出たという報告はユーザー実機確認まで行わない。
