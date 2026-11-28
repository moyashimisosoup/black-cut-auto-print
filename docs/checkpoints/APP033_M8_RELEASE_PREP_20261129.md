# APP-033 M8 | 署名付き管理版の初回導入・A→B 検収

2026-11-29 JST / PR #11（Draft）/ work_id 未登録（Session Deckの登録先未確認）。
基準 v0.7.3-rc.1 / build 70301 / eb5fb34c7cc3f4341cce91f15e747651230586a5。
基準HEADのCI 45979687173、45979687177、45979687479 はいずれも success。
今回追加: bad431e (appcast生成)、64496f2 (メタデータ試験)、a05e87c (ステージング・DLL x64確認)。新規CI、管理版・署名・実機検収は未確定。アプリ本体の版数は変更していない。既存版と異なる配布EXEを作る前に APP_VERSION と BUILD_NUMBER を更新する。

## 1. 準備（本人管理Windows担当）
- 公式 WinSparkle v0.9.4 https://github.com/vslavik/winsparkle/releases/tag/v0.9.4 の x64 DLL、同梱ライセンス、winsparkle-tool.exe を取得する。配布元と取得物のSHA256、アーキテクチャを照合。ハッシュの自己計算だけは真正性証明ではない。公開された上流ダイジェストが取得できない場合はその旨を記録し、公式配布元・版・取得手順を照合する。Inno Setup は公式配布元から取得。
- 署名鍵は Repo、ChatGPT、CIログ、同期フォルダに入れない。既存鍵がないことを確認後、本人管理の暗号化保管先で試験用鍵を一度生成。公式ツールのコマンド: `winsparkle-tool generate-key --file <Repo外の鍵ファイル>`。公開鍵のみビルドに渡す。正式鍵は検収後に別途一度生成し安全なバックアップを作る。
- テストは実運用の設定・DB・画像と分離したWindows VMまたは別ユーザープロファイルで行う。元のポータブル版と設定・DBをバックアップしておく。ステージング版もインストール先とAppMutexは本番と同じため同一プロファイルで混在させない。

## 2. ステージング A→B（公開不要）
- 本人管理のHTTPS試験配信元を用意。証明書の検証を無効化しない。初期のfeedは更新無し。試験用鍵とURLで `packaging/build_managed.ps1` の通常引数に加え `-StagingFeedUrl $stagingFeed` を指定。出力は dist/managed-staging。正式配信へ転用禁止。
- A/Bの APP_VERSION と BUILD_NUMBER は別々にし、Bは厳密に増加（例 A 0.7.3-rc.2 / 70302、B 0.7.3-rc.3 / 70303。既に使用済みの版なら次番号）。ビルド元とインストーラーSHAを記録。
- Bと同じソースのcheckoutから `python packaging/prepare_appcast.py --installer $setupB --tool $tool --private-key $testKeyFile --public-key $testPublicKey --previous-build 70302 --output $candidateXml`。新規appcast.xmlを生成する。署名は公式ツールで作成、生成コードは署名形式・ファイル名・ビルド番号・サイズを確認し、管理版に注入した公開鍵で公式 verify を実行、署名・検証前後のSHA一致を要求する。公式 v0.9.4 ソースのコマンドとstdout形式を照合済み、実行未検証。
- 生成されるURLは本番版タグ用。試験時のみXMLのenclosure URLを本人管理HTTPSのB資産URLに差し替え、Bの実バイト・長さ・署名を変えず配信する。正式配信XMLとは別フォルダで管理する。
- Aをインストールし、更新の自動適用を本人がONにして終了・再起動。Bのダウンロード、署名検証、A正常終了、Inno Setup、B再起動、更新設定の保持、印刷OFFを確認。監視中は更新しないことも確認。
- 署名欠落、破損したB、別鍵のB、同版・旧版番号、オフライン、キャンセル、インストール失敗、設定/DB/画像保持、復旧再導入を確認。WinSparkleによるバージョン比較とインストーラーの実際の版は別。過去の正規署名済みインストーラーに偽の高いメタデータ版を付けるケースも拒否できるか試験する。未確認・拒否できない場合は本番配信HOLD（インストーラー自身のバージョンガードを設計）。手動復旧は本人の明示操作に限定。
- 正式なアプリ版は更新署名とは別のAuthenticode署名がない場合、SmartScreen等の警告が出る可能性がある。警告を恒常的に無効化しない。

## 3. 本番配信（別途承認）
正式鍵で管理版を作り、同一版のBを署名し、バージョン固有のRelease資産を用意。固定のupdate-feedタグにはappcast.xmlを置く。資産を先に配信・読戻ししSHAを確認してからfeedを最後に更新。過去版の資産を同じ名前で差し替えない。公開Repoなので配布開始は本人の明示判断を得るまで実施しない。
初回のみポータブルEXEから管理版への移行が必要。旧版の常駐を終了してから管理版を導入し、設定・履歴・画像保持を確認する。以降は本人がONにした更新設定で起動時の自動適用を利用する。更新後は監視・印刷許可OFFを維持。

## 4. コピー機能・UI 残工程
現行コードを照合: SQLite CURRENT_TIMESTAMP (UTC) を履歴欄にそのまま表示。ログはJST時刻付与を要確認。プレビュー/境界は os.startfile による外部ビューアー。再加工は監視停止時のみ（印刷OFF監視中も不可）、再加工完了後は新履歴選択。次は JST表示・同一窓内の画像表示と境界切替・比較を小さく実装し、監視中再加工は排他を保つ停止→再加工→本人操作で再開の導線を優先検討。更新排他を弱めない。
Canon実機では③直接許可→④監視開始→新規スキャン3連続・A4片面1部・停止/再起動/エラーの非再送・JOB_STATUS_PRINTED有無と原稿保持/ごみ箱を検収する。

参考: https://winsparkle.org/guides/getting-started/ , https://winsparkle.org/guides/publishing-updates/ , docs/M8_AUTO_UPDATE.md。
判定: HOLD（署名配信・実機未検収）。main統合・公開未実施。次の1操作: 本人管理Windowsで公式DLL・ツールの真正性確認、試験鍵の準備、ステージング管理版Aのビルド。

## 2026-11-29 追記：公式配布物の照合
- [公式Release v0.9.4](https://github.com/vslavik/winsparkle/releases/tag/v0.9.4) API上のバイナリZIP SHA256: `6037df37fc263bd1650a1c4949681a9d40ffe991d01f35892a406cb5d103c976`。
- `packaging/prepare_winsparkle.ps1 -Destination <Repo外の新規フォルダ>` が固定URLから取得し、アーカイブのSHA256一致後のみ展開、DLL/ツール/ライセンス候補と個別SHAを表示。Windowsでの実行未確認。
- `packaging/prepare_appcast.py` は `--public-key` 必須。管理版に実際に組み込んだ公開鍵を指定し、公式 `verify` による検証が失敗した場合はXMLを出力しない。
