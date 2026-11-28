# CHECKPOINT | APP-033 M8 v0.7.4-rc.1 CI・配信準備
2026-11-29 JST / Draft PR #11 / work_id 未登録
対象HEAD 240b4aceba401fb1fc1b3ff356eb088b4a725a05。main未統合。
- 基準1ed3198のCI 3本成功。ただし追加テスト2ファイルがCI対象外、成果物名が旧版固定と判明。
- 2d963d25b55ce7369fe47f45a7cdab06360f7fbcでCI対象へ追加し成果物名をversion_info.pyから生成。途中9db4cb2のPowerShell文字列展開に起因するYAML破損を読戻しで発見し修正。
- CI 46169707065: Linux単体100、GUI8（警告1）、Windows単体100 PASS。EXE生成・パッケージ内SHA256照合成功。関連CI 46169707043, 46169707145 success。
- Artifact 15273057988 APP033-v0.7.4-rc.1-Portable-Windows / SHA256 ZIP dcf1c78977409b1c43cea6482e8af0d1448659cc2844efe66a040c8d7442b693 / 期限2026-12-06 02:19 JST。ZIP実物の再取得・再照合は未実施。
- 5118814: 公式WinSparkle v0.9.4リリースAPIの公開バイナリZIP digestを取得し、prepare_winsparkle.ps1で固定URL・一致後展開・個別SHA算出を実装。公式ツールソースも確認。
- 0bcba04 / b1f2212: prepare_appcast.pyで公開鍵指定・公式verify失敗時出力禁止とそのモックテストを追加。実署名未試験。240b4acでローカル検収手順更新。追加変更後CIは実行中。
- 次: 最新CI結果を確認、Windows本人管理環境で公式DLL・ツールを取得し、別プロファイルと試験鍵で管理版A→Bを検証。Canon連続スキャン・ごみ箱動作・UI実機検収。正式配信・main統合はHOLD。
