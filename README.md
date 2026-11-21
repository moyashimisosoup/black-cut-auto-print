# 黒部分カット自動印刷機（Black Cut Auto Print）

Canon MF244dwからWindows PCに保存されたスキャン画像を監視し、原稿の外側の黒・暗灰背景を除去して、A4用紙へ自動印刷するための個人用Windows自動処理ユーティリティ（試作・実機未検収）です。

**APP-ID：APP-033** ｜ **現在：M1 main保存／M2 [Draft PR #1](https://github.com/moyashimisosoup/black-cut-auto-print/pull/1)／M3 [Draft PR #2](https://github.com/moyashimisosoup/black-cut-auto-print/pull/2)／M4 [Draft PR #3](https://github.com/moyashimisosoup/black-cut-auto-print/pull/3)で自動印刷対応UI実装（実機未検収）** ｜ **作成元：[App Factory Issue #22](https://github.com/moyashimisosoup/app-factory/issues/22)**

## 実現したい操作

1. Windows側でアプリを起動し、監視をONにする。
2. Canon MF244dw本体から「スキャン → PC → スタート」で原稿をスキャンする。
3. Canon純正のMF Scan Utilityが専用フォルダに画像を保存する。
4. 本アプリが新規受信を検知し、紙面を見つけ、紙面**外側だけ**を白くする。
5. A4・片面・白黒・1部の印刷ジョブをWindowsドライバー経由で送信する。

スキャン開始後のPC操作を不要にすることを目指します。Canon純正のスキャン保存は利用者が確認済みです。M1では提供画像1例の画像処理、M2では模擬受信を確認しています。**Canon実機への自動印刷・排紙確認は未実施**です。

## 画像処理の必須条件

- 上・下・左・右の一辺だけ、複数辺、**四辺すべて**が暗くなる原稿に対応する。
- 黒画素を一律に消さず、文字・図版・写真・見開き中央の綴じ目を保存する。
- 外周に細い白枠があっても、外側背景の検出を試みる。
- 見開きは原則1枚として扱う。自動左右分割は将来機能。
- 傾き・回転・原寸配置の条件は仕様書で定義し、未確定の尺度を保証しない。
- 紙面検出の品質が不確実なら、**印刷せず保留**する。

## M1画像処理PoC（試作済み、印刷OFF）

- ソース：[app/m1_processing.py](app/m1_processing.py)
- 実行手順：[docs/M1_USAGE.md](docs/M1_USAGE.md)
- 合成入力テスト：[tests/test_m1_processing.py](tests/test_m1_processing.py)
- 依存定義：[requirements-m1.txt](requirements-m1.txt)
- 画像1枚を入力すると、候補紙面輪郭・保持マスク・外側白化画像・A4プレビューを保存します。
- 2026-11-21にローカル環境で合成テスト8件成功。提供実スキャン1件でもプレビューを作成できました（目視検収は未実施）。
- **M1単体は画像処理のみです。** 受信監視・Windows印刷API・GUI/EXEの後続実装はM2〜M4のDraft PRにあります。

## M4｜印刷対応オペレーター画面（Draft PR #3・実機未検収）

- [操作画面](app/m4_operator_ui.py)：受信フォルダ、印刷先選択、回転・DPI設定、監視ON/OFF、ジョブ履歴、A4プレビュー、1枚の手動試し刷り、自動印刷許可・停止。
- [印刷許可ゲート](app/m4_print_gate.py)：起動時は必ずOFF。**試し刷りの紙を本人が確認したことを、その起動中だけ記録**し、さらに別の確認操作後に自動印刷ONを許可。再起動・プリンター変更で失効。
- [M4操作ガイド](docs/M4_OPERATOR_GUIDE.md)と[合成テスト](tests/test_m4_print_gate.py)を追加。Tkinterを仮想ディスプレイで起動するGUI試験、モックの手動試し刷り→自動印刷送信試験を追加。
- [M4 CI](https://github.com/moyashimisosoup/black-cut-auto-print/actions/workflows/m4-operator-build.yml)：[Linux/Windows CI成功](https://github.com/moyashimisosoup/black-cut-auto-print/actions/runs/44905758141)。Linux単体38件＋仮想GUI3件、Windows単体38件がPASS。
- Windows用評価EXE `BlackCutPrintCandidate.exe` をCIで生成。[Actions Artifact](https://github.com/moyashimisosoup/black-cut-auto-print/actions/runs/44905758141)に7日保存。ZIPをダウンロードして破損がないこと、EXEのWindows PEヘッダを確認済み。
- **自動印刷の実機試験・排紙検収は行っていません。** Draft PRはmainへ統合しません。

## M3｜プレビュー専用GUI（印刷OFF固定・開発用）

- [画面ソース](app/m3_preview_ui.py)、[操作ガイド](docs/M3_PREVIEW.md)、[検証CHECKPOINT](docs/checkpoints/APP033_M3_PREVIEW_20261121.md)を追加。
- Windows 11向けの**署名なし確認用EXE**を[GitHub Actions run #44902861132](https://github.com/moyashimisosoup/black-cut-auto-print/actions/runs/44902861132)でビルド済み（Artifactsに保存、7日保持）。
- 「受信フォルダ」「保存先」「回転角」を設定し、監視ON/OFF、処理状態、直近A4プレビューを表示。画像処理にはM1/M2を再利用。
- Linux仮想デスクトップでGUI監視→合成JPEG受信→プレビュー作成→停止を確認。Windows実機でのexe起動・Canonスキャンはまだ未検証。
- GUIからの印刷は**機能自体が存在しない**。M2の実紙検収まで無人印刷には移行しない。

## M2監視・Windows印刷パイプライン（Draft PR・未統合）

- [監視・ジョブ状態管理](app/m2_monitor.py)：新着JPEGを検知、M1でA4加工、SQLite＋OSプロセスロックで二重送信を抑止。
- [Windows印刷アダプター](app/windows_print.py)：正確なプリンターキューにA4・片面・白黒・1部を要求。物理寸法・向き・オフラインを検査。
- [M2使い方](docs/M2_SETUP.md)：初期設定、ドライラン、明示的な手動試し刷り、自動印刷ONの順。
- [M2 CHECKPOINT](docs/checkpoints/APP033_M2_DRAFT_20261121.md)。
- Linux/Windows CIのM1+M2合成テスト26件PASS、提供実スキャン1件で監視→A4プレビュー生成→再起動後の重複なしを確認（印刷命令は送っていない）。
- **[Windows/Linux GitHub Actions CI成功](https://github.com/moyashimisosoup/black-cut-auto-print/actions/runs/44902661481)。** Windows実機印刷・ユーザーの原稿目視検収は未確認のため、Draft PRをmainに統合しない。

## 技術方針（設計段階）

- Windows 11、Canon MF244dw、MF Scan Utility
- Python 3.13、OpenCV、Pillow、pywin32、PyInstaller。watchdogは検討のみで現時点では未採用
- ローカルの専用受信フォルダを非再帰ポーリング監視（約0.8秒間隔）。JPEG安定・検証後に処理。
- ジョブ状態を永続化し、監視切替・再起動・印刷失敗による二重送信を防ぐ。
- オフライン完結を基本とし、認証情報やスキャン本文を外部送信しない。
- Windows印刷スプーラーが受け付けたことと、用紙が正常に排出されたことは区別する。

## 正本文書

- [詳細機能・技術仕様書 v0.3](docs/spec/BLACK_CUT_AUTO_PRINT_SPEC_v0.3_20261121.md)（20章、機能要件・品質ゲート・検収項目）
- [ロードマップ](docs/ROADMAP.md)
- [開発担当向けAGENTS.md](AGENTS.md)

仕様書v0.3は**2026-11-21時点の設計スナップショット**です。本文の「GitHub未保存」「APP-ID未採番」は作成当時の記録であり、現在の進捗は本READMEとSession Deck台帳を参照してください。

## 開発の順序

- **M1：画像処理PoC**：実原稿をローカルで用い、紙面境界・外側白化・A4プレビューを作り品質を検証。印刷はOFF。
- **M2：印刷パイプライン**：監視ON/OFF、保存完了待ち、状態管理、Windows印刷と安全な保留を接続。
- **M3：プレビュー専用GUI**：印刷OFFで受信と加工結果を確認。
- **M4：自動印刷対応GUI**：手動試し刷り・実紙確認・明示ON/OFF、安全な履歴を実装。トレイ常駐は別途検討。

現時点でM1はmain、M2はDraft PR #1、M3プレビューGUIはDraft PR #2、M4の自動印刷対応画面はDraft PR #3です。タスクトレイ常駐・Canon実機検収・正式公開は未実施。Webアプリ化より、無人印刷可能なローカル常駐アプリを優先します。

## 公開範囲

本リポジトリは**Public**です。著作物を含む実際の書籍スキャン、個人情報、PCの実パス、秘密情報は登録しません。公開の試験素材には自作・合成原稿のみ使用します。

## ライセンス

ライセンスは未決定です。ライセンスが明記されるまで、第三者への再利用許諾が自動的に付与されるものではありません。
