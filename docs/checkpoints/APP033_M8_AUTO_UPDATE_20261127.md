# CHECKPOINT | APP-033 M8 自動更新対応
- 日付: 2026-11-27 JST
- 正本: moyashimisosoup/black-cut-auto-print
- 作業領域: APP-033/M8 (work_idは未登録)
- branch: feature/app033-m8-winsparkle-20261127
- Draft PR: https://github.com/moyashimisosoup/black-cut-auto-print/pull/11
- 検証対象HEAD: 4d4434b573c3bd57b2bbbfb94975ad30f9a41fe8
- version: v0.7.3-rc.1
- base: PR #10 のブランチ、main未統合

## 実装・確認
WinSparkle 0.9.4の公式APIに接続するコードを実装。起動時更新確認ON、自動インストールは初期OFF・本人同意後にONを保存。監視、印刷許可、試し刷り、再加工、紙確認、終了中は更新不可。更新予約中に印刷開始不可。Windows単一起動mutex、公式DLLの照合済みSHA256を要求する管理版ビルドスクリプト、Inno Setupテンプレートを追加。設定・履歴・スキャン原稿は更新対象外。
Linux合成/仮想GUI CI成功: https://github.com/moyashimisosoup/black-cut-auto-print/actions/runs/45979490928 (78 passed in 3.77s / 8 passed, 1 warning in 10.91s).
Windowsポータブル評価版CIは実行中で、完了・成果物未確認。

## 未完了・HOLD
WinSparkle実DLL、署名鍵の安全な初回生成と保管、管理版インストーラーのコンパイル、署名済み配布物・HTTPS appcast公開は未実施。公開鍵を空に保つためポータブル評価版では自動更新は無効。GitHub公開Repoへ秘密鍵を格納しない。署名付き更新A→B、改ざん拒否、終了待ち、再起動、設定保持、旧版復旧とCanon印刷の実機確認が必要。main統合・正式自動配信は未実施。
仕様: docs/M8_AUTO_UPDATE.md
次の1操作: 安全なWindows環境で公式WinSparkle DLLと署名公開鍵を準備し、packaging/build_managed.ps1 にて初回管理版をビルドする。
