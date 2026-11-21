# APP-033/M2｜Canon MF244dw向け監視・印刷接続（試験版）

**状態：Draft PRの試験実装。実機印刷はまだ検証していません。M1のユーザー目視検収も未完了です。**
Canon純正のMF Scan UtilityでPCへ保存されたJPEGを処理し、WindowsからA4印刷する構成です。スキャナー本体側の機能は変更しません。

## 事前条件

1. Windows 11でMF244dwの通常印刷と本体からPCへのスキャン保存が動作する。
2. MF Scan Utilityから**自動印刷専用**のローカル受信フォルダへJPEG（推奨300dpi）が保存される。スキャン確認画面と別アプリ起動はOFF。
3. M1の画像加工プレビューでページ端・黒文字・図版・見開き中央を確認済みにする。
4. A4の手動試し刷りで、方向、倍率、用紙・部数を確認する。
5. PCをスリープさせず、通常ユーザー権限で実行する。秘密鍵や管理者権限は不要。

## インストール（Windows PowerShellの例）

~~~powershell
python -m pip install -r requirements-m2-windows.txt
python app/m2_monitor.py --list-printers
~~~

表示されたCanonの**正確なキュー名**をコピーする。既定のプリンターへ勝手に送らず、印刷設定はジョブ単位でのみ指定する。

## 1. ドライラン（印刷OFF）

~~~powershell
python app/m2_monitor.py --inbox "C:\ScanInbox" --output "C:\ScanResults" --rotate 90 --source-dpi 300
~~~

- コマンドが動いている間だけ監視ON。Ctrl+Cで停止。自動起動・タスクトレイはM3で開発。
- 監視開始前に既にあるファイルは無視。**開始後の新規 .jpg/.jpeg のみ**対象。
- 書込終了後2.5秒の安定を確認し、JPEG構造を検証してから画像処理。
- デフォルトでは印刷しない。結果は C:\ScanResults\jobs\ジョブID\a4_preview.png など。
- 状態DBは C:\ScanResults\jobs.sqlite3。再起動で未送信ジョブを勝手に送らない。
- JPGと同じ拡張子の無関係なファイルも新規なら検出するため、**専用フォルダだけを指定**する。

## 2. 手動試し刷り（実際に1枚出る）

~~~powershell
python app/m2_monitor.py --manual-test-print "C:\ScanResults\jobs\ジョブID\a4_preview.png" --printer "一覧に表示された正確なCanon名" --confirm-test-sheet
~~~

- 用紙と出力先を確認して実行する。これは**本当に印刷ジョブを送る操作**。
- A4、片面、1部、白黒をドライバーに要求するが、MF244dwが採用したか実機で確認。
- Windowsがジョブを受け付けても、物理的な排紙完了を保証したことにはならない。

## 3. 自動印刷ON（手動試し刷り・画質確認後のみ）

~~~powershell
python app/m2_monitor.py --inbox "C:\ScanInbox" --output "C:\ScanResults" --printer "一覧に表示された正確なCanon名" --rotate 90 --source-dpi 300 --arm-printing --confirm-reviewed
~~~

**--arm-printing と --confirm-reviewed が揃わなければ無人印刷を有効化しない。**
確認は、利用者自身が加工プレビュー、手動印刷結果、余白、方向、部数を試したことを意味する。

## 保存・再印刷の方針

| 状態 | 意味 |
| --- | --- |
| READY_REVIEW | 画像処理成功。印刷OFFで保管 |
| HOLD | 読込不可、画質不確実、監視停止など。自動印刷なし |
| SUBMITTING | 印刷API呼び出し直前にDBへ永続化した状態 |
| SUBMITTED | Windowsスプーラー受付。排紙完了ではない |
| UNKNOWN | 送信途中のエラーなど、受付有無が不明。自動再送禁止 |

同じアプリを二重起動した場合もOSのファイルロックで後から起動した側を拒否する。同じファイルイベントでは二重印刷しない。別々のスキャンとして保存された同一内容の画像はそれぞれ処理する。監視OFF中・アプリ起動前のファイルは処理しない。

## 制約と残検証
- M2はWindows用CLI試験版。GUI・タスクトレイ・EXEはM3対象。
- 監視は**専用フォルダ1件を非再帰ポーリング（0.75秒間隔）**。最初の優先順位は二重印刷防止で、将来必要ならwatchdogに変更可能。
- GitHub ActionsのCIはプリンターなしの合成試験だけ。Canon MF244dwのドライバー実機動作は未確認。
- 5種類の実画像と四辺黒の原稿、3回連続スキャンのA4・白黒・片面・1部出力、停止中の動作を実機検証してから本番扱いにする。
