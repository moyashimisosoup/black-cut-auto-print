# APP-033/M5｜タスクトレイ操作・Windows評価版

作業状態：**実装・Linux/Windows CI成功・評価EXE作成済み。Canon MF244dwの実機印刷は未検証。**

## 使い方

1. Windows 11でアプリ（評価用`BlackCutPrintTrayCandidate.exe`）を起動する。**監視OFF・自動印刷OFFから始まる**。
2. 受信フォルダ（Canon MF Scan Utility専用）と結果フォルダを分けて指定する。
3. 最初は自動印刷を許可せず、監視を開始してスキャン原稿のA4プレビューと文字欠損を確認する。
4. ウィンドウを最小化すると、Windowsの通知領域（タスクトレイ）に格納される。画面を閉じると常駐終了となるため、**作業を継続したい場合は「×」ではなく「最小化」**する。
5. タスクトレイメニュー：「画面を表示」「監視を停止」「終了」。アイコンが隠れている場合はWindowsタスクバーの通知領域を展開する。
6. 監視停止すると無人印刷許可は失効する。再度自動印刷する場合はM4の本人確認フローを踏む。
7. 終了すると監視・トレイとも停止。アプリの再起動でも自動印刷はOFFで始まる。

## 検証・制約

- タスクトレイはWindowsでのみ利用。Pythonの`pystray`（0.19.5系列）を使用する。
- タスクトレイ操作は専用スレッドからTkinterへ直接触らず、イベントキューを通してGUIメインスレッドで実行する。
- `pystray`の起動に失敗した場合、ウィンドウを保持して監視UIを使用可能にする。失敗したトレイへ最小化して取り残されない設計。
- 印刷送信中の停止でも、**既にWindowsに受け付けられた印刷ジョブを取り消したとは保証しない**。同一原稿の再印刷は自動で行わない。
- アプリ起動後の監視ONは手動。Windowsログイン時の自動起動・自動印刷の再開は実装しない。
- EXEは未署名の開発用評価版であり、実際のWindows 11環境、SmartScreen、トレイ表示、ドライバー接続を試す必要がある。
- M1の原稿内部の黒文字・写真を保護し、上下左右が暗い例を含む5種以上で紙面保持を確認すること。
- 実原稿・加工画像・個人情報・Windows固有の実パスはPublic Repoに登録しない。

## 実装・ビルド

- メインGUI：`app/m4_operator_ui.py`
- トレイモジュール：`app/m5_tray.py`
- Windows依存：`requirements-m5-windows.txt`
- 合成テスト：`tests/test_m5_tray.py`、`tests/test_m5_gui_tray.py`
- GitHub CI：`.github/workflows/m5-tray-build.yml`

Python環境での起動例：

~~~powershell
python -m pip install -r requirements-m5-windows.txt
python app/m4_operator_ui.py
~~~

[CI run #44928835667](https://github.com/moyashimisosoup/black-cut-auto-print/actions/runs/44928835667)で`BlackCutPrintTrayCandidate.exe`をArtifact ID 14715669994に保存済み（ZIP検査PASS）。GitHub Actionsのビルドは、`BlackCutPrintTrayCandidate.exe` をArtifactとして一時保存する。成果物の保存期限を超えた場合はworkflowを再実行して生成し、失効したZIPを正式リリースと誤認しない。

## フォルダの指定（2026-11-22 修正）

受信フォルダ直下の新規JPEGだけを監視します。従来は「結果保存先が受信フォルダの親」のケースまで拒否していましたが、実際には安全に監視できるため、修正版で許可しました。

| 受信 | 出力 | 判定 |
| --- | --- | --- |
| `D:\\ScanInbox` | `D:\\` | 許可（ドライブ直下に`jobs`と`jobs.sqlite3`を作成） |
| `D:\\ScanInbox` | `D:\\ScanProcessed` | **推奨・許可**（整理しやすい） |
| `D:\\ScanInbox` | `D:\\ScanInbox` | 拒否 |
| `D:\\ScanInbox` | `D:\\ScanInbox\\processed` | 拒否（受信フォルダ内に処理結果を置かない） |

ドライブ直下への保存も許可していますが、ファイル管理のため、別の専用フォルダを推奨します。元のスキャンJPEGや既存のSQLite履歴を上書きしません。

### 以前のEXEから差し替える

[更新パッケージと手順](../packaging/UPDATE_README.txt)を参照。ZIPには修正版EXE、`apply_update.bat`、`apply_update.ps1`、SHA256マニフェストを含む。以前の配布済みM4/M5 EXEのみハッシュ照合のうえ置き換えます。バッチの実行はユーザーの明示操作が必要で、自動印刷設定は有効化しません。旧EXEはバックアップとして残します。

## 未完了ゲート

- Windows実機起動/トレイ最小化・復帰・停止・終了の確認。
- Canon MF244dwの手動A4・片面・白黒・1部の排紙確認と回転・倍率検収。
- 四辺黒を含む実画像5例、連続スキャン、印刷OFF、エラー停止、二重印刷の実機確認。
- 依存PR #1→#2→#3→#4の統合、正式配布版の確定。
