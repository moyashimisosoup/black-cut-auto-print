# APP-033 / M8 自動更新（WinSparkle）

2026-11-27 JST。作業ブランチ feature/app033-m8-winsparkle-20261127。
現段階は統合コード・署名運用準備。実際の署名付き更新配信は未開始。

## OSSの比較と採用
- WinSparkle (MIT): https://github.com/vslavik/winsparkle 。DLLとネイティブ更新UI、EdDSA署名、更新時終了コールバック。採用候補 0.9.4。
- Velopack: https://github.com/velopack/velopack 。Python対応、インストール管理が有力だが現行onefile配布構成の移行が必要。
- tufup: https://github.com/dennisvang/tufup 。TUFに基づく署名付きPython更新。導入時に配信メタデータと展開設計が必要。
- PyUpdater: https://github.com/Digital-Sapphire/PyUpdater 。旧PyInstaller向け。保守性を考慮し今回は不採用。
- 一般的な更新機構を独自再実装せずWinSparkleの検証・ダウンロード・起動を使う。
- 公式API: https://winsparkle.org/c-api/checking/ , https://winsparkle.org/c-api/callbacks/ , https://winsparkle.org/guides/getting-started/

## ユーザー設定
- 起動時に更新を確認：既定ON。
- 自動更新（確認省略）：既定OFF、本人の同意でONにできる。ONを保存する。
- 手動の「更新を確認」ボタンも維持。
- 自動更新ON時はWinSparkleの check_update_with_ui_and_install を使用する。更新進捗UIは表示される。通常の通知のみは check_update_without_ui。
- 起動時に一度だけ確認。起動時に既に監視等を開始していればその回は見送る。常駐中の強制更新はしない。
- 印刷許可・監視・再加工・手動試し刷り・紙確認・終了処理中は更新を開始しない。更新予約中は新たな印刷・監視・再加工を開始できない。
- 設定・受信フォルダ・加工結果・DBを更新対象にしない。起動後の自動印刷は従来どおりOFF。

## 初回導入に残る必須条件
1. 公式WinSparkle配布物のバージョン・アーキテクチャ・SHA256を照合し、DLLと同梱ライセンスを取得。非公式DLLを検索ロードしない。
2. リリース担当が安全なローカル環境で winsparkle-tool generate-key を一度実施。秘密鍵は本人管理の暗号化保管先。GitHub公開Repo・会話・成果物に秘密鍵を含めない。公開鍵だけをビルド時に注入。
3. 管理対象のユーザー単位インストーラーを作成し、%LOCALAPPDATA%/Programs/BlackCutPrint に導入。設定は既存の %APPDATA%/BlackCutPrint のまま。既存の単体EXEは初回移行が必要。インストーラーの実行中に別インスタンスが起動・印刷しないよう単一起動と終了待ちを検収。
4. リリース用の確定インストーラーを同じ秘密鍵でEdDSA署名し、単調増加するビルド番号と sparkle:edSignature を含むappcast.xmlを生成する。feedは update-feed タグの資産、配布インストーラーは個別の変更不可な版番号のRelease資産を予定。
5. 署名なし・改変・ダウングレード・ネットワーク切断・更新キャンセル・インストール失敗・再起動後の設定保持と印刷OFFを検収。既知の旧版を再インストールできる復旧手順も確定。
6. 実機の更新 A→B と既存コピー機能の回帰検証後に署名付き更新元を公開する。評価用ZIPは自動配信しない。

公開鍵が空、DLL欠落、管理インストール外の場合は自動更新を無効化する。現時点では秘密鍵・署名済み配信物・稼働中feedがないため、設定項目は実装しても配信を有効にできない。WinSparkleの署名とWindows Authenticodeは別である。自動更新の完了を報告するのは実機A→B成功後とする。

## 実装ファイルと配信準備

- app/desktop_updater.py: WinSparkle 0.9.4 の公式APIへのctypes接続、初回鍵なしでは停止、状態排他。
- app/update_identity.py: 公開鍵（初期空）、ビルド番号70301、固定HTTPS feed。
- app/m4_operator_ui.py: 保存可能な自動確認・自動適用、本人同意、印刷操作排他。Windowsの単一起動mutexを追加。
- packaging/build_managed.ps1: 公式x64 DLLと照合済みSHA256、公式ライセンス、公開鍵、Inno Setupコンパイラのパスを受け取り、管理版EXE/インストーラーをビルド。秘密鍵は不要。ローカル作業コピーにのみ公開鍵を注入し、Repoの初期空鍵を保持。
- packaging/managed.iss: ユーザー権限の固定インストール先。アプリ終了を最大60秒待ち、強制終了しない。終了後、新版を起動。
- tests/test_desktop_updater.py: モックDLL、未設定・ポータブル版の拒否、通常確認と自動適用APIの使い分け、全ビジー状態拒否、更新中の重複禁止。

WinSparkle公式配布元: https://github.com/vslavik/winsparkle/releases/tag/v0.9.4
Inno Setup: https://jrsoftware.org/isinfo.php

管理版ビルド例（各パスとハッシュは実際の確認済み値を指定）:
```powershell
./packaging/build_managed.ps1 -PublicKey $publicKey -WinSparkleDll $dll -DllSha256 $verifiedSha256 -WinSparkleLicense $license -Iscc $iscc
```
署名鍵の生成と保全、公式DLLの実物確認、Inno Setupでのコンパイル、実際の署名済み更新A→B、公開feedの設定は未実施。CIのポータブル評価版にはDLL・公開鍵を組み込まない。未設定の機構を運用可能と称さない。

appcastのインストーラー引数はWinSparkle公式記載のInno Setup向け /SILENT /SP- を基礎に、実機での終了待ちと再起動を検収して確定する。完全無表示を目指さず進捗とエラーは表示する。
