# CHECKPOINT｜APP-033 初期化・設計文書の保全

- 日付：2026-11-21 JST
- 対象：黒部分カット自動印刷機（Black Cut Auto Print）
- APP-ID：APP-033
- 作成元：App Factory [Issue #22](https://github.com/moyashimisosoup/app-factory/issues/22)
- 正本Repo：[moyashimisosoup/black-cut-auto-print](https://github.com/moyashimisosoup/black-cut-auto-print)
- 可視性：Public（接続されたGitHubアカウントのリポジトリ一覧で確認）
- ブランチ：main
- 担当作業：App Factoryによるリポジトリ生成、仕様書と初期文書の登録
- 状態：**設計・文書格納完了／アプリ実装未着手**

## 確認済み成果
1. ユーザーがIssue #22、`moyashimisosoup/black-cut-auto-print`、Publicでの新規作成を追加承認。 `factory-approved` を付与。
2. Factory側の[作成成功コメント](https://github.com/moyashimisosoup/app-factory/issues/22#issuecomment-7062009865)を確認。新規Repoの実在・Public・main・初期READMEを接続されたGitHubから確認。
3. [仕様書v0.3](../spec/BLACK_CUT_AUTO_PRINT_SPEC_v0.3_20261121.md)の元ファイル707行を保存し、GitHubから707行の全文読戻しを確認。仕様書保存時commit：`9dc56c53e99b5aee3053f4ccebd87950c100d4c3`。
4. [README](../../README.md)、[AGENTS.md](../../AGENTS.md)、[ロードマップ](../ROADMAP.md)を作成/更新し、GitHubで各ファイルを読戻し確認。
5. [Session Deck全体台帳](https://github.com/moyashimisosoup/session-deck/blob/main/docs/APP_PORTFOLIO.md)へAPP-033を登録。台帳コミット：`073378d80aae9c9cee92f87f48a110eb9a1396f2`。

## 公開範囲とセキュリティ
- ユーザー提供の実スキャン画像は**公開していない**。仕様書は試験観察のみを記す。
- 認証情報・固有のWindowsファイルパス・個人情報は配置しない。
- 新規Public Repo作成とWebサービス公開・アプリ配布は別工程。GitHub Pages公開なし。

## 未実施・未検証
- 画像処理ソースコード、画質の合格判定、Windows実機での自動印刷、タスクトレイ、EXE。
- 実原稿の自動的な紙面境界検出の成否。四辺黒や外周白枠は設計対象であって実証済みではない。
- ブランチ保護ルール・CIの追加と実動作はこの初期化工程では未実施。
- 仕様書v0.3の「APP-ID未採番／GitHub未保存」は作成当時のスナップショット文言。現状態はREADME・本CHECKPOINT・台帳が優先。

## 次の1操作
M1：実スキャン画像はローカルで保持し、公開Repoには合成素材だけを置いて、原稿の紙面境界・外側白化・A4プレビューを確認する最小PoCを実装する（**印刷OFF**）。
