# CHECKPOINT｜APP-033 M7 許可ボタンの操作順改善

- 日付：2026-11-22 JST
- APP-ID / work_id：APP-033 / APP033-M7-APPROVAL-UI-01
- Repo：`moyashimisosoup/black-cut-auto-print`（Public）
- 作業ブランチ：`feature/app033-m7-approval-ui-20261122`
- [Draft PR #9](https://github.com/moyashimisosoup/black-cut-auto-print/pull/9)（base：統合RC Draft PR #8のブランチ）
- 版数：`v0.7.1-rc.1`
- 開発状態：**許可過程のUI再配置を実装し、Linux単体59件・Xvfb仮想GUI7件PASS。Windows CI成功・評価EXEとZIPのSHA/CRC検査済み。実機の自動印刷検収は未完了。**
- main：**未統合**。従来の監視・印刷の安全境界を維持。

## 実機フィードバック

利用者はWindowsでCanon MF240 Seriesキューと試し刷り操作を確認した。その後、自動印刷の許可まで進めるボタンが画面内に分散していたため、実機操作に即して横一列に並べ替えるよう依頼した。今回の変更はボタンの導線を中心とし、受信・加工・印刷のパイプラインには変更を加えていない。

## 実装変更

1. `app/m4_operator_ui.py`の画面で、履歴下の`LabelFrame`内に**①1枚試し刷り → ②紙の結果を確認 → ③自動印刷を許可 → ④監視開始（自動印刷）**を横一列に配置。
2. 許可がないときの④は「監視のみ開始（印刷OFF）」と表示し、監視だけの利用を妨げない。
3. 「監視を停止（準備へ戻る）」「自動印刷をOFFにする」は下の別行。プレビュー／赤い境界の確認ボタンは印刷の許可と混同しない別行へ配置。
4. 状態に合わせ「①を使う」「②実際の紙を確認」「③許可」「④監視開始」「監視中は停止」の次の操作を表示。
5. ボタンの有効・無効は従来の`PrintGate`、手動印刷スレッド、再加工スレッド、監視スレッドから判断。**起動時OFF、紙を確認するまで無人印刷不可、監視停止で許可失効**を維持。
6. テスト`tests/test_m4_simulated_workflow.py`に4ボタンの同一行・左からの順序と、①→④の各状態/案内文・監視停止の検証を追加。
7. 配布バージョン`v0.7.1-rc.1`、旧`v0.7.0-rc.1`EXEの既知ハッシュを更新バッチ対象へ追加。ハッシュ不一致のEXEは差し替えない。

## 検査・残工程

- [GitHub Actions #45006899362](https://github.com/moyashimisosoup/black-cut-auto-print/actions/runs/45006899362)：Linux単体**59 PASS**、Xvfb仮想GUI**7 PASS**（warning 1）、失敗なし。
- [更新バッチCI #45006899399](https://github.com/moyashimisosoup/black-cut-auto-print/actions/runs/45006899399)：Windows上の正常・不一致SHA検査がsuccess。
- [x] [GitHub Actions #45006899362](https://github.com/moyashimisosoup/black-cut-auto-print/actions/runs/45006899362)：**Linux/Windowsの両ジョブsuccess**。Windows単体59件PASS、未署名PyInstaller EXE生成、パッケージ内部のSHA照合PASS。
- [x] [M4既存互換 CI #45006899393](https://github.com/moyashimisosoup/black-cut-auto-print/actions/runs/45006899393)：Linux/Windows合格。
- [x] ZIPのGitHub Actions Artifact `APP033-v0.7.1-rc.1-TrimDepth-Windows-update`（ID `14748291929`、`2026-11-29T09:20:24Z`有効期限記録）を取得し、`APP033-v0.7.1-rc.1-ApprovalUI-Windows.zip`として読戻し。
- [x] ZIP SHA-256 `e34e950815fb12f84805e8039ced4c31d28028e98efeef1727f552e9fdfba3bd`、7ファイルCRC PASS。`VERSION.txt`=`v0.7.1-rc.1`、Windows EXE（72,416,991 bytes）の`MZ`ヘッダー確認。
- [x] EXE SHA-256 `11e58bed06bddc9f779e50fb341295bf1730871df2285b69cbb782798e374698`で同梱`new_exe_sha256.txt`と一致。
- [ ] 利用者Windowsで新EXEのGUI・プリンタ確認、Canon実紙印刷/無人印刷の実機検収。
- [ ] Windows実機で新版ボタンの並びと条件付き有効化を確認する。
- [ ] Canonで手動1枚と無人印刷・連続3回・停止・再起動・オフライン状態を検収する。
- [ ] main統合と正式配布（Canon実機検収後に別途判断）。

## 今回は変更しない範囲

過去の相談にあったJSTへの履歴日時の変換、同じウィンドウ内への画像プレビュー埋込み、監視中の再加工操作の再設計は本PRの対象外。許可ボタンの明確化に集中し、これらは別のUI改善として扱う。実機で未確認の完了を報告しない。

## 次の1操作

最新版のWindows評価EXEを取得したら、印刷OFFのままで起動し、原稿を選択→①試し刷り→②紙の結果を確認→③自動印刷許可→④監視開始の操作順が画面で分かるか確認。既存の実紙・安全検収は別ゲートのまま。
