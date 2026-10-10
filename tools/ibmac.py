#!/usr/bin/env python3
"""Mac (targetRuntime MacOSX.Cocoa) xib -> NIBArchive compiler.

Apple's ibtool 27.0 writes macOS nibs in the same NIBArchive container as iOS
(oracle: NNW Mac xibs compiled on macstudio; the container is tools/nibarchive.py).
Inside, the graph is the classic keyed NSIBObjectData shape: NSRoot (File's
Owner), NSConnections, NSObjectsKeys/Values (each top-level object and its
container), NSOidsKeys/Values (1..n in document order). Rules below are oracle
probes, not app knowledge:

- Document walk: owner NSCustomObject, NSVisibleWindows set, NSConnections; then
  every outlet connection in document order, building its destination object on
  first reference; then NSObjectsKeys (document pre-order: NSApplication proxy,
  views with their cells, each view's constraints after its subtree), the parent
  array, oids, accessibility arrays.
- Windows: NSWindowTemplate with a fixed key order; NSWTFlags = 0x60000000 |
  hidesOnDeactivate<<31 | strut bits (left 0x080000, right 0x100000, top
  0x200000, bottom 0x400000; no position mask means all four);
  NSWindowIsRestorable stores the INVERSE of the restorable attribute.
- Views: NSvFlags = 256 | autoresizing bits (translatesAutoresizingMaskIntoConstraints
  =NO pins 268; hidden adds 0x80000000 and widens the int); custom views encode
  as NSClassSwapper with the mangled _TtC class name.
- Constraints: the iOS ordering rule (tools/ibtool._constraint_order) reproduces
  Apple's Mac order byte for byte; guides are real NSLayoutGuide objects.
- System catalog colors resolve to Generic Gray 2.2 (ICC_DATA, extracted from
  the oracle output); NSControl/NSTextFieldCell flags and the inverted
  NSControlUsesSingleLineMode are probed constants (tests/ibtool/golden-mac).
"""

ICC_DATA = bytes.fromhex("""\
0000119c6170706c020000006d6e74724752415958595a2007dc00080017000f002e000f6163
73704150504c000000006e6f6e65000000000000000000000000000000000000f6d600010000
0000d32d6170706c000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000564657363000000c0000000796473636d0000013c
0000081a637072740000095800000023777470740000097c000000146b545243000009900000
080c64657363000000000000001f47656e6572696320477261792047616d6d6120322e322050
726f66696c650000000000000000000000000000000000000000000000000000000000000000
0000000000000000000000000000000000000000000000000000000000000000000000000000
0000000000000000000000006d6c7563000000000000001f0000000c736b534b0000002e0000
01846461444b0000003a000001b26361455300000038000001ec7669564e0000004000000224
707442520000004a00000264756b55410000002c000002ae667246550000003e000002da6875
485500000034000003187a6854570000001a0000034c6b6f4b5200000022000003666e624e4f
0000003a000003886373435a00000028000003c26865494c00000024000003ea726f524f0000
002a0000040e646544450000004e00000438697449540000004e000004867376534500000038
000004d47a68434e0000001a0000050c6a614a500000002600000526656c47520000002a0000
054c7074504f00000052000005766e6c4e4c00000040000005c8657345530000004c00000608
7468544800000032000006547472545200000024000006866669464900000046000006aa6872
48520000003e000006f0706c504c0000004a0000072e617245470000002c0000077872755255
0000003a000007a4656e55530000003c000007de005601610065006f006200650063006e00e1
002000730069007600e1002000670061006d006100200032002c003200470065006e00650072
00690073006b00200067007200e500200032002c0032002000670061006d006d0061002d0070
0072006f00660069006c00470061006d006d006100200064006500200067007200690073006f
0073002000670065006e00e8007200690063006100200032002e003200431ea5007500200068
00ec006e00680020004d00e000750020007800e1006d0020004300680075006e006700200047
0061006d006d006100200032002e003200500065007200660069006c002000470065006e00e9
007200690063006f002000640061002000470061006d0061002000640065002000430069006e
007a0061007300200032002c00320417043004330430043b044c043d04300020004700720061
0079002d04330430043c043000200032002e003200500072006f00660069006c0020006700e9
006e00e90072006900710075006500200067007200690073002000670061006d006d00610020
0032002c003200c1006c00740061006c00e1006e006f007300200073007a00fc0072006b0065
002000670061006d006d006100200032002e0032901a75287070968e51495ea60032002e0032
82725f6963cf8ff0c77cbc180020d68cc0c90020ac10b9c800200032002e00320020d504b85c
d30cc77c00470065006e0065007200690073006b00200067007200e5002000670061006d006d
006100200032002c0032002d00700072006f00660069006c004f006200650063006e00e10020
01610065006400e1002000670061006d006100200032002e003205d205d005de05d4002005d0
05e405d505e8002005db05dc05dc05d900200032002e003200470061006d0061002000670072
0069002000670065006e0065007200690063010300200032002c00320041006c006c00670065
006d00650069006e006500730020004700720061007500730074007500660065006e002d0050
0072006f00660069006c002000470061006d006d006100200032002c003200500072006f0066
0069006c006f002000670072006900670069006f002000670065006e0065007200690063006f
002000640065006c006c0061002000670061006d006d006100200032002c003200470065006e
0065007200690073006b00200067007200e500200032002c0032002000670061006d006d0061
00700072006f00660069006c666e901a70705ea67cfb65700032002e003263cf8ff065874ef6
4e00822c30b030ec30a430ac30f330de00200032002e0032002030d730ed30d530a130a430eb
039303b503bd03b903ba03cc0020039303ba03c103b90020039303ac03bc03bc03b100200032
002e003200500065007200660069006c002000670065006e00e9007200690063006f00200064
0065002000630069006e007a0065006e0074006f0073002000640061002000470061006d006d
006100200032002c00320041006c00670065006d00650065006e0020006700720069006a0073
002000670061006d006d006100200032002c0032002d00700072006f006600690065006c0050
0065007200660069006c002000670065006e00e9007200690063006f00200064006500200067
0061006d006d0061002000640065002000670072006900730065007300200032002c00320e23
0e310e070e2a0e350e410e010e210e210e320e400e010e230e220e4c0e170e310e480e270e44
0e1b00200032002e003200470065006e0065006c0020004700720069002000470061006d0061
00200032002c00320059006c00650069006e0065006e0020006800610072006d00610061006e
002000670061006d006d006100200032002c00320020002d00700072006f006600690069006c
006900470065006e006500720069010d006b006900200047007200610079002000470061006d
006d006100200032002e0032002000700072006f00660069006c0055006e0069007700650072
00730061006c006e0079002000700072006f00660069006c00200073007a00610072006f015b
00630069002000670061006d006d006100200032002c0032063a06270645062700200032002e
003200200644064806460020063106450627062f064a0020063906270645041e043104490430
044f00200441043504400430044f002004330430043c043c043000200032002c0032002d043f
0440043e04440438043b044c00470065006e0065007200690063002000470072006100790020
00470061006d006d006100200032002e0032002000500072006f00660069006c006500007465
787400000000436f70797269676874204170706c6520496e632e2c2032303132000058595a20
000000000000f35100010000000116cc63757276000000000000040000000005000a000f0014
0019001e00230028002d00320037003b00400045004a004f00540059005e00630068006d0072
0077007c00810086008b00900095009a009f00a400a900ae00b200b700bc00c100c600cb00d0
00d500db00e000e500eb00f000f600fb01010107010d01130119011f0125012b01320138013e
0145014c0152015901600167016e0175017c0183018b0192019a01a101a901b101b901c101c9
01d101d901e101e901f201fa0203020c0214021d0226022f02380241024b0254025d02670271
027a0284028e029802a202ac02b602c102cb02d502e002eb02f50300030b03160321032d0338
0343034f035a03660372037e038a039603a203ae03ba03c703d303e003ec03f9040604130420
042d043b0448045504630471047e048c049a04a804b604c404d304e104f004fe050d051c052b
053a05490558056705770586059605a605b505c505d505e505f6060606160627063706480659
066a067b068c069d06af06c006d106e306f507070719072b073d074f076107740786079907ac
07bf07d207e507f8080b081f08320846085a086e0882089608aa08be08d208e708fb09100925
093a094f09640979098f09a409ba09cf09e509fb0a110a270a3d0a540a6a0a810a980aae0ac5
0adc0af30b0b0b220b390b510b690b800b980bb00bc80be10bf90c120c2a0c430c5c0c750c8e
0ca70cc00cd90cf30d0d0d260d400d5a0d740d8e0da90dc30dde0df80e130e2e0e490e640e7f
0e9b0eb60ed20eee0f090f250f410f5e0f7a0f960fb30fcf0fec1009102610431061107e109b
10b910d710f511131131114f116d118c11aa11c911e81207122612451264128412a312c312e3
1303132313431363138313a413c513e5140614271449146a148b14ad14ce14f0151215341556
1578159b15bd15e0160316261649166c168f16b216d616fa171d17411765178917ae17d217f7
181b18401865188a18af18d518fa19201945196b199119b719dd1a041a2a1a511a771a9e1ac5
1aec1b141b3b1b631b8a1bb21bda1c021c2a1c521c7b1ca31ccc1cf51d1e1d471d701d991dc3
1dec1e161e401e6a1e941ebe1ee91f131f3e1f691f941fbf1fea20152041206c209820c420f0
211c2148217521a121ce21fb22272255228222af22dd230a23382366239423c223f0241f244d
247c24ab24da250925382568259725c725f726272657268726b726e827182749277a27ab27dc
280d283f287128a228d429062938296b299d29d02a022a352a682a9b2acf2b022b362b692b9d
2bd12c052c392c6e2ca22cd72d0c2d412d762dab2de12e162e4c2e822eb72eee2f242f5a2f91
2fc72ffe3035306c30a430db3112314a318231ba31f2322a3263329b32d4330d3346337f33b8
33f1342b3465349e34d83513354d358735c235fd3637367236ae36e937243760379c37d73814
3850388c38c839053942397f39bc39f93a363a743ab23aef3b2d3b6b3baa3be83c273c653ca4
3ce33d223d613da13de03e203e603ea03ee03f213f613fa23fe24023406440a640e74129416a
41ac41ee4230427242b542f7433a437d43c044034447448a44ce45124555459a45de46224667
46ab46f04735477b47c04805484b489148d7491d496349a949f04a374a7d4ac44b0c4b534b9a
4be24c2a4c724cba4d024d4a4d934ddc4e254e6e4eb74f004f494f934fdd5027507150bb5106
5150519b51e65231527c52c75313535f53aa53f65442548f54db5528557555c2560f565c56a9
56f75744579257e0582f587d58cb591a596959b85a075a565aa65af55b455b955be55c355c86
5cd65d275d785dc95e1a5e6c5ebd5f0f5f615fb36005605760aa60fc614f61a261f56249629c
62f06343639763eb6440649464e9653d659265e7663d669266e8673d679367e9683f689668ec
6943699a69f16a486a9f6af76b4f6ba76bff6c576caf6d086d606db96e126e6b6ec46f1e6f78
6fd1702b708670e0713a719571f0724b72a67301735d73b87414747074cc7528758575e1763e
769b76f8775677b37811786e78cc792a798979e77a467aa57b047b637bc27c217c817ce17d41
7da17e017e627ec27f237f847fe5804780a8810a816b81cd8230829282f4835783ba841d8480
84e3854785ab860e867286d7873b879f8804886988ce8933899989fe8a648aca8b308b968bfc
8c638cca8d318d988dff8e668ece8f368f9e9006906e90d6913f91a89211927a92e3934d93b6
9420948a94f4955f95c99634969f970a977597e0984c98b89924999099fc9a689ad59b429baf
9c1c9c899cf79d649dd29e409eae9f1d9f8b9ffaa069a0d8a147a1b6a226a296a306a376a3e6
a456a4c7a538a5a9a61aa68ba6fda76ea7e0a852a8c4a937a9a9aa1caa8fab02ab75abe9ac5c
acd0ad44adb8ae2daea1af16af8bb000b075b0eab160b1d6b24bb2c2b338b3aeb425b49cb513
b58ab601b679b6f0b768b7e0b859b8d1b94ab9c2ba3bbab5bb2ebba7bc21bc9bbd15bd8fbe0a
be84beffbf7abff5c070c0ecc167c1e3c25fc2dbc358c3d4c451c4cec54bc5c8c646c6c3c741
c7bfc83dc8bcc93ac9b9ca38cab7cb36cbb6cc35ccb5cd35cdb5ce36ceb6cf37cfb8d039d0ba
d13cd1bed23fd2c1d344d3c6d449d4cbd54ed5d1d655d6d8d75cd7e0d864d8e8d96cd9f1da76
dafbdb80dc05dc8add10dd96de1cdea2df29dfafe036e0bde144e1cce253e2dbe363e3ebe473
e4fce584e60de696e71fe7a9e832e8bce946e9d0ea5beae5eb70ebfbec86ed11ed9cee28eeb4
ef40efccf058f0e5f172f1fff28cf319f3a7f434f4c2f550f5def66df6fbf78af819f8a8f938
f9c7fa57fae7fb77fc07fc98fd29fdbafe4bfedcff6dffff
""".replace("\n", ""))

SRGB_ICC_DATA = bytes.fromhex("""\
00000c484c696e6f021000006d6e74725247422058595a2007ce000200090006
00310000616373704d5346540000000049454320735247420000000000000000
000000000000f6d6000100000000d32d48502020000000000000000000000000
0000000000000000000000000000000000000000000000000000000000000000
0000001163707274000001500000003364657363000001840000006c77747074
000001f000000014626b707400000204000000147258595a0000021800000014
6758595a0000022c000000146258595a0000024000000014646d6e6400000254
00000070646d6464000002c400000088767565640000034c0000008676696577
000003d4000000246c756d69000003f8000000146d6561730000040c00000024
74656368000004300000000c725452430000043c0000080c675452430000043c
0000080c625452430000043c0000080c7465787400000000436f707972696768
74202863292031393938204865776c6574742d5061636b61726420436f6d7061
6e790000646573630000000000000012735247422049454336313936362d322e
31000000000000000000000012735247422049454336313936362d322e310000
0000000000000000000000000000000000000000000000000000000000000000
0000000000000000000000000000000058595a20000000000000f35100010000
000116cc58595a200000000000000000000000000000000058595a2000000000
00006fa2000038f50000039058595a2000000000000062990000b785000018da
58595a2000000000000024a000000f840000b6cf646573630000000000000016
49454320687474703a2f2f7777772e6965632e63680000000000000000000000
1649454320687474703a2f2f7777772e6965632e636800000000000000000000
0000000000000000000000000000000000000000000000000000000000000000
0000000064657363000000000000002e4945432036313936362d322e31204465
6661756c742052474220636f6c6f7572207370616365202d2073524742000000
00000000000000002e4945432036313936362d322e312044656661756c742052
474220636f6c6f7572207370616365202d207352474200000000000000000000
00000000000000000000000064657363000000000000002c5265666572656e63
652056696577696e6720436f6e646974696f6e20696e2049454336313936362d
322e3100000000000000000000002c5265666572656e63652056696577696e67
20436f6e646974696f6e20696e2049454336313936362d322e31000000000000
000000000000000000000000000000000000000076696577000000000013a4fe
00145f2e0010cf140003edcc0004130b00035c9e0000000158595a2000000000
004c09560050000000571fe76d65617300000000000000010000000000000000
00000000000000000000028f0000000273696720000000004352542063757276
000000000000040000000005000a000f00140019001e00230028002d00320037
003b00400045004a004f00540059005e00630068006d00720077007c00810086
008b00900095009a009f00a400a900ae00b200b700bc00c100c600cb00d000d5
00db00e000e500eb00f000f600fb01010107010d01130119011f0125012b0132
0138013e0145014c0152015901600167016e0175017c0183018b0192019a01a1
01a901b101b901c101c901d101d901e101e901f201fa0203020c0214021d0226
022f02380241024b0254025d02670271027a0284028e029802a202ac02b602c1
02cb02d502e002eb02f50300030b03160321032d03380343034f035a03660372
037e038a039603a203ae03ba03c703d303e003ec03f9040604130420042d043b
0448045504630471047e048c049a04a804b604c404d304e104f004fe050d051c
052b053a05490558056705770586059605a605b505c505d505e505f606060616
0627063706480659066a067b068c069d06af06c006d106e306f507070719072b
073d074f076107740786079907ac07bf07d207e507f8080b081f08320846085a
086e0882089608aa08be08d208e708fb09100925093a094f09640979098f09a4
09ba09cf09e509fb0a110a270a3d0a540a6a0a810a980aae0ac50adc0af30b0b
0b220b390b510b690b800b980bb00bc80be10bf90c120c2a0c430c5c0c750c8e
0ca70cc00cd90cf30d0d0d260d400d5a0d740d8e0da90dc30dde0df80e130e2e
0e490e640e7f0e9b0eb60ed20eee0f090f250f410f5e0f7a0f960fb30fcf0fec
1009102610431061107e109b10b910d710f511131131114f116d118c11aa11c9
11e81207122612451264128412a312c312e31303132313431363138313a413c5
13e5140614271449146a148b14ad14ce14f01512153415561578159b15bd15e0
160316261649166c168f16b216d616fa171d17411765178917ae17d217f7181b
18401865188a18af18d518fa19201945196b199119b719dd1a041a2a1a511a77
1a9e1ac51aec1b141b3b1b631b8a1bb21bda1c021c2a1c521c7b1ca31ccc1cf5
1d1e1d471d701d991dc31dec1e161e401e6a1e941ebe1ee91f131f3e1f691f94
1fbf1fea20152041206c209820c420f0211c2148217521a121ce21fb22272255
228222af22dd230a23382366239423c223f0241f244d247c24ab24da25092538
2568259725c725f726272657268726b726e827182749277a27ab27dc280d283f
287128a228d429062938296b299d29d02a022a352a682a9b2acf2b022b362b69
2b9d2bd12c052c392c6e2ca22cd72d0c2d412d762dab2de12e162e4c2e822eb7
2eee2f242f5a2f912fc72ffe3035306c30a430db3112314a318231ba31f2322a
3263329b32d4330d3346337f33b833f1342b3465349e34d83513354d358735c2
35fd3637367236ae36e937243760379c37d738143850388c38c839053942397f
39bc39f93a363a743ab23aef3b2d3b6b3baa3be83c273c653ca43ce33d223d61
3da13de03e203e603ea03ee03f213f613fa23fe24023406440a640e74129416a
41ac41ee4230427242b542f7433a437d43c044034447448a44ce45124555459a
45de4622466746ab46f04735477b47c04805484b489148d7491d496349a949f0
4a374a7d4ac44b0c4b534b9a4be24c2a4c724cba4d024d4a4d934ddc4e254e6e
4eb74f004f494f934fdd5027507150bb51065150519b51e65231527c52c75313
535f53aa53f65442548f54db5528557555c2560f565c56a956f75744579257e0
582f587d58cb591a596959b85a075a565aa65af55b455b955be55c355c865cd6
5d275d785dc95e1a5e6c5ebd5f0f5f615fb36005605760aa60fc614f61a261f5
6249629c62f06343639763eb6440649464e9653d659265e7663d669266e8673d
679367e9683f689668ec6943699a69f16a486a9f6af76b4f6ba76bff6c576caf
6d086d606db96e126e6b6ec46f1e6f786fd1702b708670e0713a719571f0724b
72a67301735d73b87414747074cc7528758575e1763e769b76f8775677b37811
786e78cc792a798979e77a467aa57b047b637bc27c217c817ce17d417da17e01
7e627ec27f237f847fe5804780a8810a816b81cd8230829282f4835783ba841d
848084e3854785ab860e867286d7873b879f8804886988ce8933899989fe8a64
8aca8b308b968bfc8c638cca8d318d988dff8e668ece8f368f9e9006906e90d6
913f91a89211927a92e3934d93b69420948a94f4955f95c99634969f970a9775
97e0984c98b89924999099fc9a689ad59b429baf9c1c9c899cf79d649dd29e40
9eae9f1d9f8b9ffaa069a0d8a147a1b6a226a296a306a376a3e6a456a4c7a538
a5a9a61aa68ba6fda76ea7e0a852a8c4a937a9a9aa1caa8fab02ab75abe9ac5c
acd0ad44adb8ae2daea1af16af8bb000b075b0eab160b1d6b24bb2c2b338b3ae
b425b49cb513b58ab601b679b6f0b768b7e0b859b8d1b94ab9c2ba3bbab5bb2e
bba7bc21bc9bbd15bd8fbe0abe84beffbf7abff5c070c0ecc167c1e3c25fc2db
c358c3d4c451c4cec54bc5c8c646c6c3c741c7bfc83dc8bcc93ac9b9ca38cab7
cb36cbb6cc35ccb5cd35cdb5ce36ceb6cf37cfb8d039d0bad13cd1bed23fd2c1
d344d3c6d449d4cbd54ed5d1d655d6d8d75cd7e0d864d8e8d96cd9f1da76dafb
db80dc05dc8add10dd96de1cdea2df29dfafe036e0bde144e1cce253e2dbe363
e3ebe473e4fce584e60de696e71fe7a9e832e8bce946e9d0ea5beae5eb70ebfb
ec86ed11ed9cee28eeb4ef40efccf058f0e5f172f1fff28cf319f3a7f434f4c2
f550f5def66df6fbf78af819f8a8f938f9c7fa57fae7fb77fc07fc98fd29fdba
fe4bfedcff6dffff
""".replace("\n", ""))

# colorSpace="custom" colors: attrs -> (NSRGB/NSWhite payload, space).
# NSRGB is ColorSync's own display conversion of the linear components
# (oracle values; identity only for white/gray).
CUSTOM_COLORS = {  # -> (NSRGB display conversion, space, NSLinearExposure)
    ("srgb", None, "1", "1", "1", "0.0"):
        (b"1 1 1 0\x00", "srgb", b"1"),
    ("gray", "0.0", None, None, None, "0.0"):
        (b"0 0\x00", "gray", b"1"),
    ("srgb", None, "0.030999999493360519", "0.41600000858306885",
     "0.93300002813339233", "1"):
        (b"0.0493131876 0.3120345175 0.9147195816\x00", "srgb", b"0"),
    ("srgb", None, "1", "0", "0", "1"):
        (b"0.9859541655 0 0.02694000863\x00", "srgb", b"1"),
}


import math
import os
import struct
import sys
import xml.etree.ElementTree as ET

_TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _TOOLS)


def _load_ibtool():
    import importlib.machinery
    import importlib.util
    path = os.path.join(_TOOLS, "ibtool")
    loader = importlib.machinery.SourceFileLoader("ibtool_tool", path)
    spec = importlib.util.spec_from_loader("ibtool_tool", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


I = _load_ibtool()  # Builder primitives, constraint ordering, mangling


def set_target_module(module):
    """The running ibtool's --module (SwiftPM maps <pkg>_<target>); the script
    run and this import are separate module instances, so hand it over."""
    import sys
    print(f"set_target_module({module!r})", file=sys.stderr)
    I.TARGET_MODULE = module
import keyorder  # noqa: E402
import nibarchive as N  # noqa: E402

# NSWindowStyleMask bits (probe: titled 1, closable 2, miniaturizable 4,
# resizable 8, utility 16, docModal 64, fullSizeContentView 32768).
STYLE_MASK = {"titled": 1, "closable": 2, "miniaturizable": 4, "resizable": 8,
              "utility": 16, "docModal": 64, "fullSizeContentView": 32768,
              "nonactivatingPanel": 128, "texturedBackground": 256,
              "unifiedTitleAndToolbar": 4096, "borderless": 0}
STRUTS = {"leftStrut": 0x080000, "rightStrut": 0x100000,
          "topStrut": 0x200000, "bottomStrut": 0x400000}
COLLECTION_BEHAVIOR = {"fullScreenPrimary": 128, "fullScreenAuxiliary": 256,
                      "canJoinAllSpaces": 1, "moveToActiveSpace": 2}
TABBING_MODE = {"automatic": 0, "preferred": 1, "disallowed": 2}
TOOLBAR_STYLE = {"automatic": 0, "expanded": 1, "preference": 2, "unified": 3,
                 "unifiedCompact": 4}
# NSControlTextAlignment (probe: left 0, center 1, right 2, justified 3,
# natural 4) is NOT NSTextAlignment; NSCellFlags2 stores NSTextAlignment << 26.
CONTROL_ALIGN = {"left": 0, "center": 1, "right": 2, "justified": 3, "natural": 4}
TEXT_ALIGN = {"left": 0, "right": 1, "center": 2, "justified": 3, "natural": 4}
# NSLineBreakMode (Foundation): the NSControl key stores the enum, NSCellFlags2
# a 0x200-multiples bit pattern probed per mode (wordWrap 0, clipping 0x400,
# truncatingTail 0x800, truncatingMiddle 0xA00). Keys are the xib attributes.
LINE_BREAK = {"wordWrap": 0, "charWrap": 1, "clipping": 2, "truncatingHead": 3,
              "truncatingTail": 4, "truncatingMiddle": 5}
LINE_BREAK_FLAGS2 = {"wordWrap": 0, "charWrap": 0x200, "clipping": 0x400,
                     "truncatingHead": 0xC00, "truncatingTail": 0x800,
                     "truncatingMiddle": 0xA00}
META_FONTS = {  # metaFont -> (NSSize, NSfFlags); probed names and flags
    "system": (13.0, 1044), "smallSystem": (11.0, 3100),
    "miniSystem": (9.0, 3100), "boldSystem": (13.0, 2072),
    "smallBoldSystem": (11.0, 6204), "smallSystemBold": (11.0, 3357), "label": (10.0, 3100),
    "toolTips": (11.0, 3100), "menu": (13.0, 1558), "message": (13.0, 1558),
    "palette": (11.0, 3100), "titleBar": (13.0, 1044),
    "systemDetail": (11.0, 3100), "cellTitle": (12.0, 4883),
    "systemBold": (13.0, 2072),
}
FONT_NAMES = {"system": ".AppleSystemUIFont", "smallSystem": ".AppleSystemUIFont",
              "miniSystem": ".AppleSystemUIFont", "boldSystem": ".AppleSystemUIFontBold",
              "smallBoldSystem": ".AppleSystemUIFontBold", "systemBold": ".AppleSystemUIFontBold",
              "smallSystemBold": ".AppleSystemUIFontBold",
              "cellTitle": ".AppleSystemUIFont", "menu": ".AppleSystemUIFont",
              "message": ".AppleSystemUIFont", "palette": ".AppleSystemUIFont",
              "label": ".AppleSystemUIFont", "toolTips": ".AppleSystemUIFont",
              "titleBar": ".AppleSystemUIFont", "systemDetail": ".AppleSystemUIFont"}
# System catalog colors resolve to Generic Gray Gamma 2.2 at compile time
# (oracle probe, Xcode 27.0): name -> (NSWhite payload, NSComponents payload).
CATALOG_COLORS = {
    "controlColor": (b"0.602715373\x00", b"0.6666666667 1"),
    "labelColor": (b"0\x00", b"0 1"),
    "secondaryLabelColor": (b"0.2637968361\x00", b"0.3333333333 1"),
    "tertiaryLabelColor": (b"0.4375036359\x00", b"0.4666666667 1"),
    "quaternaryLabelColor": (b"0.6477062404\x00", b"0.6 1"),
    "textColor": (b"0\x00", b"0 1"),
    "placeholderTextColor": (b"0.6477062404\x00", b"0.6 1"),
    "selectedTextColor": (b"0\x00", b"0 1"),
    "textBackgroundColor": (b"1\x00", b"1 1"),
    "selectedTextBackgroundColor": (b"0.602715373\x00", b"0.6666666667 1"),
    "keyboardFocusIndicatorColor": (b"0.213Second\x00", b"0.213 1"),
    "controlAccentColor": (b"0.09019608\x00", b"0.352941 0.666667 0.913725 1"),
    "controlTextColor": (b"0\x00", b"0 1"),
    "disabledControlTextColor": (b"0.4375036359\x00", b"0.4666666667 1"),
    "controlBackgroundColor": (b"0.602715373\x00", b"0.6666666667 1"),
    "_sourceListBackgroundColor": (b"0.602715373\x00", b"0.6666666667 1"),
    "selectedControlTextColor": (b"0\x00", b"0 1"),
    "windowBackgroundColor": (b"0.9493610263\x00", b"0.9493610263 1"),
    "windowFrameTextColor": (b"0\x00", b"0 1"),
    "underPageBackgroundColor": (b"0.8 got\x00", b"0.8 1"),
    "findHighlightColor": (b"1\x00", b"1 0.9 0.35 1"),
    "unemphasizedSelectedTextBackgroundColor": (b"0.9015956522\x00", b"0.9015956522 1"),
    "alternatingEvenBackgroundColor": (b"1\x00", b"1 1"),
    "alternatingOddBackgroundColor": (b"0.9658410256\x00", b"0.9658410256 1"),
    "linkColor": (b"0.16151028\00", b"0.039216 0.423529 0.815686 1"),
    "separatorColor": (b"0.874618\00", b"0.874618 1"),
    "gridColor": (b"0.4246723652\x00", b"0.5 1"),
    "headerTextColor": (b"0\x00", b"0 1"),
    "headerColor": (b"1\x00", b"1 1"),
    "highlightColor": (b"0.8470830959\x00", b"0.733333 0.827451 0.898039 1"),
    "selectedMenuItemTextColor": (b"1\x00", b"1 1"),
    "selectedContentBackgroundColor": (b"0.2826356863\x00", b"0.258824 0.513725 0.870588 1"),
    "unemphasizedSelectedContentBackgroundColor": (b"0.9015956522\x00", b"0.9015956522 1"),
}


def int_fit(v):
    """Apple picks the smallest signed width; negatives go INT64
    (probe About: 0/13/16 -> INT8, 256/2049 -> INT16, -1 -> INT64)."""
    if v < 0:
        return (N.INT64, v)
    if v < 128:
        return (N.INT8, v)
    if v < 32768:
        return (N.INT16, v)
    if v < 0x80000000:
        return (N.INT32, v)
    return (N.INT64, v)


def _fmt_g(v):
    f = float(v)
    return str(int(f)) if f == int(f) and abs(f) < 1e15 else f"{f:g}"


def _fmt10(v):
    return f"{float(v):.10g}"


# textStyle -> (NSSize, UICTFontTextStyle usage, bold); oracle probes
TEXT_STYLES = {
    "callout": (12.0, "Callout", False),
    "headline": (13.0, "Headline", True),
    "subheadline": (11.0, "Subhead", False),
    "title3": (15.0, "Title3", False),
}


def _i32(v):
    return v - 0x100000000 if v > 0x7FFFFFFF else v


def _localizable(b, owner_id, text, where, suffix=".title"):
    """User string in a .lproj output: NSLocalizableString{bytes, NSKey=ownerId.title,
    NSDev}; a pooled plain string elsewhere or for the empty string."""
    if text == "" or not b.localize:
        return b.string(text)
    o = b.new("NSLocalizableString")
    o.add("NS.bytes", N.DATA, text.encode("utf-8"))
    o.add("NSKey", *b.ref(b.string(owner_id + suffix)))
    o.add("NSDev", *b.ref(b.string(text)))
    return o


def _rect(el, key, where):
    r = el.find(f"rect[@key='{key}']")
    if r is None:
        raise I.XibError(f"<{el.tag}> is missing rect {key!r} ({where})")
    return "{{%s, %s}, {%s, %s}}" % (_fmt_g(r.get("x", 0)), _fmt_g(r.get("y", 0)),
                                     _fmt_g(r.get("width")), _fmt_g(r.get("height")))


def _window_rect(el, where):
    """NSWindowRect: a window visible at launch with no initialPositionMask
    compiles centered on its screenRect (About {1035,566} == center of
    2560x1410 for 490x278); everything else keeps the saved contentRect."""
    r = el.find("rect[@key='contentRect']")
    if r is None:
        raise I.XibError(f"<{el.tag}> is missing rect 'contentRect' ({where})")
    if (el.get("visibleAtLaunch") != "NO"
            and el.find("windowPositionMask[@key='initialPositionMask']") is None):
        s = el.find("rect[@key='screenRect']")
        if s is not None:
            x = (float(s.get("width")) - float(r.get("width"))) / 2
            y = (float(s.get("height")) - float(r.get("height"))) / 2
            return "{{%s, %s}, {%s, %s}}" % (_fmt_g(x), _fmt_g(y),
                                             _fmt_g(r.get("width")),
                                             _fmt_g(r.get("height")))
    return "{{%s, %s}, {%s, %s}}" % (_fmt_g(r.get("x", 0)), _fmt_g(r.get("y", 0)),
                                     _fmt_g(r.get("width")), _fmt_g(r.get("height")))


def _size(el, key, where):
    v = el.find(f"value[@key='{key}']")
    if v is None:
        raise I.XibError(f"<{el.tag}> is missing value {key!r} ({where})")
    return "{%s, %s}" % (_fmt_g(v.get("width")), _fmt_g(v.get("height")))


class _Late:
    """A forward object reference: the destination object is allocated later."""

    def __init__(self):
        self.obj = None


class _DeferredPairs:
    """(obj, parent) key pairs computed later: prototype cells build lazily
    at connection time, after the window tree produced the pair list."""

    def __init__(self, fn):
        self.fn = fn


class MacBuilder(I.Builder):
    """Adds the Mac-side object pools (fonts, colors, guides) to the iOS Builder."""

    def __init__(self):
        super().__init__()
        self.fonts = {}
        self.catalog_colors = {}
        self.white_colors = {}
        self.custom_colors = {}
        self.cursors = {}
        self.blue = None
        self.red = None
        self.image_decls = {}   # <image name=...> elements from <resources>
        self.named_color_els = {}  # <namedColor name=...> inner <color>
        self.named_colors = {}  # built namedColor wrappers by name
        self.colorspace = None  # shared Generic Gray space
        self.srgbspace = None   # shared sRGB space (custom colors)
        self.late = []          # unresolved _Late refs
        self.cons_order = {}    # view xib id -> constraint ids in Apple order
        self.grid_meta = {}     # gridView xib id -> (rows, cols, {cellId: cell})
        self.localize = False   # .lproj xibs wrap user strings
        self.nums = {}          # NSNumber intern pool by numeric value
        self.bool_nums = {}     # NSNumber bool pool for binding options (inverted)
        self.img_sources = {}   # NSButtonImageSource intern pool by name

    def number(self, typ, v):
        """Apple pools NSNumbers across the whole archive by value (probe About:
        the oid for 11 reuses the style descriptor's NS.dblval 11.0 object)."""
        o = self.nums.get(float(v))
        if o is None:
            o = self.new("NSNumber")
            o.add("NS.dblval" if typ == N.DOUBLE else "NS.intval", typ, v)
            self.nums[float(v)] = o
        return o

    def ref(self, obj):
        if isinstance(obj, _Late):
            self.late.append(obj)
            return (N.OBJREF, obj)
        return super().ref(obj)

    def int_fit32(self, v):
        if -128 <= v < 128:
            return (N.INT8, v)
        if -32768 <= v < 32768:
            return (N.INT16, v)
        return (N.INT32, v)

    def font(self, fd_el, where, appearance_key=True):
        text_style = fd_el.get("textStyle")
        if text_style is not None:
            key = ("style", text_style)
            if key in self.fonts:
                return self.fonts[key]
            size, usage, bold = TEXT_STYLES[text_style]
            o = self.new("NSFont")
            o.add("NSName", *self.ref(self.string(
                ".AppleSystemUIFontBold" if bold else ".AppleSystemUIFont")))
            o.add("NSSize", *self.float64(size))
            o.add("NSfFlags", *int_fit(16))
            o.add("NSTextStyleDescriptor", *self.ref(self._style_descriptor(usage, size)))
            o.add("NSHasWidth", *self.boolean(True))
            self.fonts[key] = o
            return o
        if fd_el.get("usesAppearanceFont") == "YES":
            key = ("appearance", appearance_key)
            if key in self.fonts:
                return self.fonts[key]
            o = self.new("NSFont")
            o.add("NSName", *self.ref(self.string(".AppleSystemUIFont")))
            if appearance_key:
                o.add("NSFontUsesAppearanceFontSize", *self.boolean(False))
            o.add("NSSize", *self.float64(13.0))
            o.add("NSfFlags", *int_fit(1044))
            self.fonts[key] = o
            return o
        name = fd_el.get("name")
        if name is not None and fd_el.get("metaFont") is None:
            key = ("name", name, fd_el.get("size"))
            if key in self.fonts:
                return self.fonts[key]
            o = self.new("NSFont")
            o.add("NSName", *self.ref(self.string(name)))
            o.add("NSSize", *self.float64(float(fd_el.get("size", 13))))
            o.add("NSfFlags", *int_fit(16))
            self.fonts[key] = o
            return o
        meta = fd_el.get("metaFont")
        if meta is None:
            raise I.XibError(f"<font> without metaFont ({where})")
        size, flags = META_FONTS.get(meta, (None, None))
        if size is None:
            raise I.XibError(f"<font> metaFont {meta!r} not probed ({where})")
        if fd_el.get("size"):
            size = float(fd_el.get("size"))
        if meta not in FONT_NAMES:
            raise I.XibError(f"<font> metaFont {meta!r} not probed ({where})")
        key = (meta, size)
        if key in self.fonts:
            return self.fonts[key]
        o = self.new("NSFont")
        o.add("NSName", *self.ref(self.string(FONT_NAMES[meta])))
        o.add("NSSize", *self.float64(size))
        o.add("NSfFlags", *int_fit(flags))
        self.fonts[key] = o
        return o

    def _style_descriptor(self, usage, size):
        key = ("desc", usage)
        if key in self.fonts:
            return self.fonts[key]
        o = self.new("NSFontDescriptor")
        attrs = self.new("NSDictionary")
        attrs.add("NSInlinedValue", *self.boolean(False))
        attrs.add("UINibEncoderEmptyKey", *self.ref(self.string("NSCTFontSizeCategoryAttribute")))
        attrs.add("UINibEncoderEmptyKey", *self.ref(self.number(N.INT8, 3)))
        attrs.add("UINibEncoderEmptyKey", *self.ref(self.string("NSCTFontUIUsageAttribute")))
        attrs.add("UINibEncoderEmptyKey", *self.ref(self.string("UICTFontTextStyle" + usage)))
        attrs.add("UINibEncoderEmptyKey", *self.ref(self.string("NSFontSizeAttribute")))
        attrs.add("UINibEncoderEmptyKey", *self.ref(self.number(N.DOUBLE, size)))
        o.add("NSFontDescriptorAttributes", *self.ref(attrs))
        o.add("NSFontDescriptorOptions", N.INT64, 2147517444)
        self.fonts[key] = o
        return o

    def srgb_space(self):
        if self.srgbspace is None:
            cs = self.new("NSColorSpace")
            cs.add("NSID", *self.int8(7))
            data = self.new("NSData")
            data.add("NS.bytes", N.DATA, SRGB_ICC_DATA)
            cs.add("NSICC", *self.ref(data))
            self.srgbspace = cs
        return self.srgbspace

    def custom_color(self, el, where):
        """colorSpace="custom": ColorSync archives the linear components plus its
        own display conversion (NSRGB). Only the corpus colors are probed."""
        shape = "gray" if el.get("white") is not None else "srgb"
        keys = ("white", "alpha") if shape == "gray" else ("red", "green", "blue", "alpha")
        comps = " ".join(_fmt10(el.get(k, "1")) for k in keys)
        probe = CUSTOM_COLORS.get((shape, el.get("white"), el.get("red"),
                                   el.get("green"), el.get("blue"),
                                   el.get("alpha")))
        if probe is None:
            raise I.XibError(f"custom color {sorted(el.attrib.items())} not probed ({where})")
        payload, space, exposure = probe
        key = (payload, space)
        if key in self.custom_colors:
            return self.custom_colors[key]
        o = self.new("NSColor")
        if space == "gray":
            o.add("NSColorSpace", N.INT8, 3)
            o.add("NSWhite", N.DATA, payload)
            o.add("NSCustomColorSpace", *self.ref(self.color_space()))
        else:
            o.add("NSColorSpace", N.INT8, 1)
            o.add("NSRGB", N.DATA, payload)
            o.add("NSCustomColorSpace", *self.ref(self.srgb_space()))
        o.add("NSComponents", N.DATA, comps.encode())
        o.add("NSLinearExposure", N.DATA, exposure)
        self.custom_colors[key] = o
        return o

    def color_space(self):
        if self.colorspace is None:
            cs = self.new("NSColorSpace")
            cs.add("NSID", *self.int8(9))
            cs.add("NSModel", *self.int8(0))
            data = self.new("NSData")
            data.add("NS.bytes", N.DATA, ICC_DATA)
            cs.add("NSICC", *self.ref(data))
            self.colorspace = cs
        return self.colorspace

    def white_color(self, white, comps):
        key = (white, comps)
        if key in self.white_colors:
            return self.white_colors[key]
        o = self.new("NSColor")
        o.add("NSColorSpace", *self.int8(3))
        o.add("NSWhite", N.DATA, white)
        o.add("NSCustomColorSpace", *self.ref(self.color_space()))
        o.add("NSComponents", N.DATA, comps)
        o.add("NSLinearExposure", N.DATA, b"1")
        self.white_colors[key] = o
        return o

    def catalog_color(self, catalog, name, where):
        if catalog != "System":
            raise I.XibError(f"color catalog {catalog!r} not probed ({where})")
        if name == "linkColor":
            return self._named_blue(name)
        if name == "textInsertionPointColor":
            return self._named_blue(name, where=where, inner_name="systemBlueColor")
        if name == "systemBlueColor":
            return self._named_blue(name)
        if name == "systemRedColor":
            # golden AccountsFeedbin [50..52]: wrapper around a space-1 sRGB
            # red (components "1 0 0 1", ColorSync display conversion pinned)
            if name in self.catalog_colors:
                return self.catalog_colors[name]
            o = self.new("NSColor")
            o.add("NSColorSpace", *self.int8(6))
            o.add("NSCatalogName", *self.ref(self.string(catalog)))
            o.add("NSColorName", *self.ref(self.string(name)))
            o.add("NSColor", *self.ref(self._red_color()))
            self.catalog_colors[name] = o
            return o
        if name == "_sourceListBackgroundColor":
            # golden SidebarView [49]: own wrapper whose inner color is the
            # controlBackgroundColor catalog WRAPPER object
            if name in self.catalog_colors:
                return self.catalog_colors[name]
            inner = self.catalog_color("System", "controlBackgroundColor", where)
            o = self.new("NSColor")
            o.add("NSColorSpace", *self.int8(6))
            o.add("NSCatalogName", *self.ref(self.string(catalog)))
            o.add("NSColorName", *self.ref(self.string(name)))
            o.add("NSColor", *self.ref(inner))
            self.catalog_colors[name] = o
            return o
        if name == "separatorColor":
            # golden CurrentActivity [79]: the wrapper's inner color is the
            # gridColor WRAPPER object (separator's own values never archive);
            # the wrapper allocates before its inner
            if name in self.catalog_colors:
                return self.catalog_colors[name]
            o = self.new("NSColor")
            o.add("NSColorSpace", *self.int8(6))
            o.add("NSCatalogName", *self.ref(self.string(catalog)))
            o.add("NSColorName", *self.ref(self.string(name)))
            o.add("NSColor", *self.ref(self.catalog_color("System", "gridColor", where)))
            self.catalog_colors[name] = o
            return o
        if name not in CATALOG_COLORS:
            raise I.XibError(f"System color {name!r} not probed ({where})")
        if name in self.catalog_colors:
            return self.catalog_colors[name]
        o = self.new("NSColor")
        o.add("NSColorSpace", *self.int8(6))
        o.add("NSCatalogName", *self.ref(self.string(catalog)))
        o.add("NSColorName", *self.ref(self.string(name)))
        o.add("NSColor", *self.ref(self.white_color(*CATALOG_COLORS[name])))
        self.catalog_colors[name] = o
        return o

    def _named_blue(self, name, where=None, inner_name=None):
        """Catalog color wrapper around the shared blue (probe About:
        systemBlueColor -> raw sRGB blue; textInsertionPointColor -> the
        systemBlueColor wrapper; linkColor -> the raw blue). The wrapper
        object is allocated before its inner color (probe About [74..78])."""
        if name in self.catalog_colors:
            return self.catalog_colors[name]
        o = self.new("NSColor")
        o.add("NSColorSpace", *self.int8(6))
        o.add("NSCatalogName", *self.ref(self.string("System")))
        o.add("NSColorName", *self.ref(self.string(name)))
        if inner_name is not None:
            inner = self.catalog_color("System", inner_name, where)
        else:
            inner = self._blue_color()
        o.add("NSColor", *self.ref(inner))
        self.catalog_colors[name] = o
        return o

    def _blue_color(self):
        """systemBlueColor archives as a space-1 sRGB color (oracle About)."""
        if self.blue is None:
            o = self.new("NSColor")
            o.add("NSColorSpace", N.INT8, 1)
            o.add("NSRGB", N.DATA, b"0 0 0.9981992245\x00")
            o.add("NSCustomColorSpace", *self.ref(self.srgb_space()))
            o.add("NSComponents", N.DATA, b"0 0 1 1")
            o.add("NSLinearExposure", N.DATA, b"1")
            self.blue = o
        return self.blue

    def _red_color(self):
        """systemRedColor inner (probe AccountsFeedbin [52])."""
        if self.red is None:
            o = self.new("NSColor")
            o.add("NSColorSpace", N.INT8, 1)
            o.add("NSRGB", N.DATA, b"0.9859541655 0 0.02694000863\x00")
            o.add("NSCustomColorSpace", *self.ref(self.srgb_space()))
            o.add("NSComponents", N.DATA, b"1 0 0 1")
            o.add("NSLinearExposure", N.DATA, b"1")
            self.red = o
        return self.red

    def named_color(self, name, where):
        """<namedColor> asset resource (probe AccountsFeedbin [31..35]):
        catalog wrapper '#$assets-mainBundleID' around the inline sRGB color,
        catalog name fixed regardless of the bundle."""
        if name in self.named_colors:
            return self.named_colors[name]
        el = self.named_color_els.get(name)
        if el is None:
            raise I.XibError(f"namedColor {name!r} not declared in <resources> ({where})")
        o = self.new("NSColor")
        o.add("NSColorSpace", *self.int8(6))
        o.add("NSCatalogName", *self.ref(self.string("#$assets-mainBundleID")))
        o.add("NSColorName", *self.ref(self.string(name)))
        o.add("NSColor", *self.ref(self.custom_color(el, where)))
        self.named_colors[name] = o
        return o


def _classref(b, cls, module, provider):
    if provider == "target" and I.TARGET_MODULE:
        module = I.TARGET_MODULE  # customModuleProvider=target: --module wins
    o = b.new("IBClassReference")
    o.add("IBClassName", *b.ref(b.string(cls)))
    o.add("IBModuleName", *(b.ref(b.string(module)) if module else (N.NIL, None)))
    o.add("IBModuleProvider", *(b.ref(b.string(provider)) if provider else (N.NIL, None)))
    return o


def _custom_object(b, el, class_name, where):
    o = b.new("NSCustomObject")
    o.add("IBClassReference", *b.ref(_classref(b, el.get("customClass") or class_name,
                                               el.get("customModule"),
                                               el.get("customModuleProvider"))))
    o.add("NSClassName", *b.ref(b.string(class_name)))
    return o


def _translates(el):
    """translatesAutoresizingMaskIntoConstraints=NO, but a fixedFrame canvas
    element keeps the autoresizing path (probe About field/scrollView)."""
    return (el.get("translatesAutoresizingMaskIntoConstraints") == "NO"
            and el.get("fixedFrame") != "YES")


def _vflags(el, where):
    translates = _translates(el)
    if translates:
        v = 268
    else:
        v = 256
        m = el.find("autoresizingMask[@key='autoresizingMask']")
        if m is not None:
            for flag, bit in I.RESIZE_FLAGS.items():
                if m.get(flag) == "YES":
                    v |= bit
    hidden = el.get("hidden") == "YES"
    if hidden:
        v |= 0x80000000
        return v - 0x100000000, N.INT64
    return v, N.INT16


GUIDE_IDENT = {"safeArea": "NSViewSafeAreaLayoutGuide",
               "layoutMargins": "NSViewLayoutMarginsGuide"}
GUIDE_TYPE = {"safeArea": 2, "layoutMargins": 1}


def _guide(b, gid, guides, guide_kinds, where):
    """A real NSLayoutGuide, allocated on first reference (probe DetailView pbD)."""
    if gid in guides:
        return guides[gid]
    kind = guide_kinds[gid]
    o = b.new("NSLayoutGuide")
    o.add("NSLayoutGuideIdentifier", *b.ref(b.string(GUIDE_IDENT[kind])))
    o.add("NSShouldBeArchived", *b.boolean(False))
    o.add("NSLayoutGuideNegativeSize", *b.boolean(False))
    o.add("NSLayoutGuideLockedToOwningView", *b.boolean(False))
    syscons = b.new("NSMutableArray")
    syscons.add("NSInlinedValue", *b.boolean(False))
    o.add("NSLayoutGuideSystemConstraints", *b.ref(syscons))
    guides[gid] = o
    return o


def _ref_to(b, item, owner_obj, owner_id, id_map, guides, guide_kinds, where,
            lates=None):
    if item is None or item == "-2":
        return b.ref(owner_obj)
    if item in guides:
        return b.ref(guides[item])
    if item in guide_kinds:
        return b.ref(_guide(b, item, guides, guide_kinds, where))
    if item in id_map:
        return b.ref(id_map[item])
    if lates is not None:
        late = _Late()
        lates.append((late, item))
        return b.ref(late)
    raise I.XibError(f"reference to {item!r} before it is built ({where})")


def _constraint(b, el, owner_obj, owner_id, id_map, guides, guide_kinds, where,
                lates=None):
    """Mac NSLayoutConstraint: the iOS value order; guides are real objects."""
    o = b.new("NSLayoutConstraint")
    first = el.get("firstItem")
    o.add("NSFirstItem", *_ref_to(b, first, owner_obj, owner_id, id_map,
                                  guides, guide_kinds, where, lates))
    fa = el.get("firstAttribute")
    if fa is None:
        raise I.XibError(f"<constraint> missing firstAttribute ({where})")
    o.add("NSFirstAttributeV2", *b.int8(I.ATTRIBUTES.get(fa, I.MARGIN_V2.get(fa, 0))))
    o.add("NSFirstAttribute", *b.int8(I.ATTRIBUTES.get(I.MARGIN_BASE.get(fa, fa), 0)))
    mul = el.get("multiplier")
    if mul is not None and float(mul) != 1.0:
        # golden AccountsReaderAPI [205]: multiplier="0.951613" archives as
        # float32 widened to double (0.9516130089759827)
        o.add("NSMultiplier", N.DOUBLE,
              struct.unpack("<f", struct.pack("<f", float(mul)))[0])
    rel = I.RELATIONS.get(el.get("relation", "equal"))
    if rel is not None:
        o.add("NSRelation", *b.int8(rel))
    second = el.get("secondItem")
    if second is not None:
        o.add("NSSecondItem", *_ref_to(b, second, owner_obj, owner_id, id_map,
                                       guides, guide_kinds, where, lates))
        sa = el.get("secondAttribute")
        if sa is None:
            raise I.XibError(f"<constraint> secondItem without secondAttribute ({where})")
        o.add("NSSecondAttributeV2", *b.int8(I.ATTRIBUTES.get(sa, I.MARGIN_V2.get(sa, 0))))
        o.add("NSSecondAttribute", *b.int8(I.ATTRIBUTES.get(I.MARGIN_BASE.get(sa, sa), 0)))
    if el.get("symbolic") == "YES":
        o.add("NSSymbolicConstant", *b.ref(b.string("NSSpace")))
        o.add("NSShouldBeArchived", *b.boolean(False))
    elif el.get("constant") is not None:
        c = float(el.get("constant"))
        o.add("NSConstantV2", *b.float64(c))
        o.add("NSShouldBeArchived", *b.boolean(False))
        o.add("NSConstant", *b.float64(c))
    else:
        o.add("NSShouldBeArchived", *b.boolean(False))
    if el.get("id"):
        id_map[el.get("id")] = o
    return o


def _cell(b, el, control, where, owner_id=None, cell_cls="NSTextFieldCell",
          id_map=None):
    """<textFieldCell>: NSCellFlags/Flags2 from the probe matrix."""
    o = b.new(cell_cls)
    flags = 0x4000000
    flags2 = TEXT_ALIGN[el.get("alignment", "natural")] << 26
    lb = el.get("lineBreakMode", "wordWrap")
    if lb not in LINE_BREAK:
        raise I.XibError(f"lineBreakMode {lb!r} not probed ({where})")
    flags2 |= LINE_BREAK_FLAGS2[lb]
    if el.get("controlSize") == "small":
        # probe GeneralPreferencesView [130]/[163] (the corpus's only two
        # controlSize=small textFieldCells): flags2 bit 17
        flags2 |= 0x20000
    if lb != "wordWrap":
        flags |= 0x40
    if el.get("scrollable") == "YES":
        flags |= 0x100000
    if el.get("selectable") == "YES":
        flags |= 0x200000 | 0x1
    if el.get("allowsUndo") == "NO":
        flags2 |= 0x1000
    if el.get("sendsActionOnEndEditing") == "YES":
        flags2 |= 0x400000
    if el.get("usesSingleLineMode") == "YES":
        flags2 |= 0x40
    if el.get("editable") == "YES":
        flags |= 0x10000000 | 0x400000
        # probe AddLocal/Feedbin/ReaderAPI (no state attr: 0x14700041) vs
        # RenameSheet/ShareVC (state="on": +0x80000000)
        if el.get("state") == "on":
            flags |= 0x80000000
        # probe AddFeedSheet/FeedInspector vs RenameSheet/AddFolder: the 0x400
        # flags2 bit only joins editable when the cell is also scrollable
        if el.get("scrollable") == "YES":
            flags2 |= 0x400
    elif el.get("editable") is not None:
        flags |= 0x400000
    if flags > 0x7FFFFFFF or flags < -0x80000000:
        o.add("NSCellFlags", N.INT64, flags - 0x100000000 if flags > 0x7FFFFFFF else flags)
    else:
        o.add("NSCellFlags", N.INT32, flags)
    o.add("NSCellFlags2", N.INT32, _i32(flags2))
    title_el = el.find("string[@key='title']")
    title = el.get("title", title_el.text if title_el is not None and title_el.text else "")
    # formatter cells drop NSContents (probe DinosaursWindow pSw); plain cells
    # archive it even when empty (probe DetailView [22])
    if el.find("numberFormatter[@key='formatter']") is None:
        o.add("NSContents", *b.ref(_localizable(b, owner_id or "", title, where)))
    fd = el.find("font[@key='font']")
    if fd is None:
        raise I.XibError(f"<textFieldCell> without <font> ({where})")
    o.add("NSSupport", *b.ref(b.font(fd, where)))
    fel = el.find("numberFormatter[@key='formatter']")
    if fel is not None:
        fobj = _number_formatter(b, fel, where)
        if id_map is not None and fel.get("id"):
            id_map[fel.get("id")] = fobj
        o.add("NSFormatter", *b.ref(fobj))
    if el.get("placeholderString") is not None:
        o.add("NSPlaceholderString",
              *b.ref(_localizable(b, el.get("id") or "", el.get("placeholderString"),
                                  where, suffix=".placeholderString")))
    o.add("NSControlView", *b.ref(control))
    for key in ("backgroundColor", "textColor"):
        c = el.find(f"color[@key='{key}']")
        if c is None:
            raise I.XibError(f"<textFieldCell> without {key} color ({where})")
        if c.get("catalog") != "System":
            raise I.XibError(f"{key} color without catalog=System ({where})")
        if key == "backgroundColor" and el.get("drawsBackground") is not None:
            o.add("NSDrawsBackground", *b.boolean(el.get("drawsBackground") != "YES"))
        o.add("NSBackgroundColor" if key == "backgroundColor" else "NSTextColor",
              *b.ref(b.catalog_color(c.get("catalog"),
                                     "controlTextColor"
                                     if key == "textColor"
                                     and c.get("name") == "textColor"
                                     else c.get("name"), where)))
    return o


def _number_formatter(b, el, where):
    """<numberFormatter> -> NSNumberFormatter (probe DinosaursWindow [46]):
    fixed Apple template; only behavior/style/width/digits follow the xib."""
    ns = el.get("numberStyle", "decimal")
    if ns != "decimal":
        raise I.XibError(f"numberStyle {ns!r} not probed ({where})")
    beh = el.get("formatterBehavior", "default10_4")
    if beh != "default10_4":
        raise I.XibError(f"formatterBehavior {beh!r} not probed ({where})")
    maxfrac = int(el.get("maximumFractionDigits", 3))
    fmt = "#,##0" + ("." + "#" * maxfrac if maxfrac else "")

    def bool_num(v):
        key = ("boolval", bool(v))
        n = b.bool_nums.get(key)
        if n is None:
            n = b.new("NSNumber")
            n.add("NS.boolval", N.TRUE if v else N.FALSE, None)
            b.bool_nums[key] = n
        return n

    o = b.new("NSNumberFormatter")
    d = b.new("NSMutableDictionary")
    d.add("NSInlinedValue", *b.boolean(False))
    for k, kind, v in (
            ("allowsFloats", "bool", False),
            ("alwaysShowsDecimalSeparator", "bool", True),
            ("formatWidth", "int", int(el.get("formatWidth", -1))),
            ("formatterBehavior", "int", 1040),
            ("generatesDecimalNumbers", "bool", True),
            ("groupingSize", "int", 3),
            ("lenient", "bool", True),
            ("maximumFractionDigits", "int", maxfrac),
            ("maximumIntegerDigits", "int",
             int(el.get("maximumIntegerDigits", 2000000000))),
            ("minimumFractionDigits", "int",
             int(el.get("minimumFractionDigits", 0))),
            ("minimumIntegerDigits", "int",
             int(el.get("minimumIntegerDigits", 1))),
            ("negativeInfinitySymbol", "str", "-\u221e"),
            ("nilSymbol", "str", ""),
            ("numberStyle", "int", 1),
            ("paddingPosition", "int", 0),
            ("positiveInfinitySymbol", "str", "+\u221e"),
            ("roundingMode", "int", 4),
            ("secondaryGroupingSize", "int", 0),
            ("usesGroupingSeparator", "bool", False)):
        d.add("UINibEncoderEmptyKey", *b.ref(b.string(k)))
        if kind == "str":
            d.add("UINibEncoderEmptyKey", *b.ref(b.string(v)))
        elif kind == "int":
            d.add("UINibEncoderEmptyKey", *b.ref(b.number(*int_fit(v))))
        else:
            d.add("UINibEncoderEmptyKey", *b.ref(bool_num(v)))
    o.add("NS.attributes", *b.ref(d))
    o.add("NS.positiveformat", *b.ref(b.string(fmt)))
    o.add("NS.negativeformat", *b.ref(b.string(fmt)))
    o.add("NS.positiveattrs", *(N.NIL, None))
    o.add("NS.negativeattrs", *(N.NIL, None))
    o.add("NS.zero", *(N.NIL, None))
    nilattr = b.new("NSAttributedString")
    nilattr.add("NSString", *b.ref(b.string("")))
    o.add("NS.nil", *b.ref(nilattr))
    nan = b.new("NSAttributedString")
    nan.add("NSString", *b.ref(b.string("NaN")))
    nanattrs = b.new("NSDictionary")
    nanattrs.add("NSInlinedValue", *b.boolean(False))
    nan.add("NSAttributes", *b.ref(nanattrs))
    o.add("NS.nan", *b.ref(nan))
    ph = b.new("NSDecimalNumberPlaceholder")
    ph.add("NS.exponent", *b.int8(0))
    ph.add("NS.length", *b.int8(0))
    ph.add("NS.negative", *b.boolean(False))
    ph.add("NS.compact", *b.boolean(True))
    ph.add("NS.mantissa.bo", *b.int8(1))
    ph.add("NS.mantissa", N.DATA, b"\x00" * 16)
    o.add("NS.min", *b.ref(ph))
    o.add("NS.max", *b.ref(ph))
    rh = b.new("NSDecimalNumberHandler")
    rh.add("NS.roundingmode", *b.int8(3))
    rh.add("NS.raise.overflow", *b.boolean(False))
    rh.add("NS.raise.underflow", *b.boolean(False))
    rh.add("NS.raise.dividebyzero", *b.boolean(False))
    o.add("NS.rounding", *b.ref(rh))
    o.add("NS.decimal", *b.ref(b.string(".")))
    o.add("NS.thousand", *b.ref(b.string(",")))
    o.add("NS.hasthousands", *b.boolean(False))
    o.add("NS.localized", *b.boolean(False))
    o.add("NS.allowsfloats", *b.boolean(False))
    return o


def _field(b, el, where, superview, id_map, parent=None):
    """<textField>/<secureTextField>: NSTextField/NSSecureTextField
    (NSClassSwapper when customClass, probe About LinkLabel) with its cell;
    returns (obj, [(obj, parent)])."""
    guides = {}
    secure = el.tag == "secureTextField"
    o = b.new("NSClassSwapper" if el.get("customClass")
              else "NSSecureTextField" if secure else "NSTextField")
    if el.get("customClass"):
        o.add("NSClassName", *b.ref(b.string(I._swift_class(el))))
        o.add("NSOriginalClassName",
              *b.ref(b.string("NSSecureTextField" if secure else "NSTextField")))
    o.add("NSNextResponder", *(b.ref(superview) if superview is not None else (N.NIL, None)))
    o.add("NSNibTouchBar", *(N.NIL, None))
    v, vt = _vflags(el, where)
    o.add("NSvFlags", vt, v)
    o.add("NSFrame", *b.ref(b.string(_rect(el, "frame", where))))
    o.add("NSSuperview", *b.ref(superview))
    if el.get("wantsLayer") == "YES":
        # probe ActivityLog label [98]: any view-kind element with wantsLayer
        o.add("NSViewIsLayerTreeHost", *b.boolean(False))
    o.add("NSViewWantsBestResolutionOpenGLSurface", *b.boolean(False))
    if _translates(el):
        o.add("NSDoNotTranslateAutoresizingMask", *b.boolean(False))
    # probe FeedInspector [38]: the constraints array precedes the priority
    # strings on textFields
    cons_el = el.find("constraints")
    cons = []
    if cons_el is not None and cons_el.findall("constraint"):
        carr = b.new("NSArray")
        carr.add("NSInlinedValue", *b.boolean(False))
        els = I._constraint_order(el, cons_el.findall("constraint"), where, mac=True)
        for c in els:
            con = _constraint(b, c, o, el.get("id"), id_map, guides, {}, where)
            carr.add("UINibEncoderEmptyKey", *b.ref(con))
            cons.append(con)
        b.cons_order[el.get("id")] = [c.get("id") for c in els]
        o.add("NSViewConstraints", *b.ref(carr))
    h, v2 = el.get("horizontalHuggingPriority"), el.get("verticalHuggingPriority")
    if (h is not None and h != "250") or (v2 is not None and v2 != "750"):
        o.add("NSHuggingPriority",
              *b.ref(b.string("{%s, %s}" % (_fmt_g(h or 250), _fmt_g(v2 or 750)))))
    h, v2 = (el.get("horizontalCompressionResistancePriority"),
             el.get("verticalCompressionResistancePriority"))
    if (h is not None and h != "750") or (v2 is not None and v2 != "750"):
        o.add("NSAntiCompressionPriority",
              *b.ref(b.string("{%s, %s}" % (_fmt_g(h or 750), _fmt_g(v2 or 750)))))
    o.add("IBNSSafeAreaLayoutGuide", *(N.NIL, None))
    o.add("IBNSLayoutMarginsGuide", *(N.NIL, None))
    o.add("IBNSClipsToBounds", *b.int8(0))
    o.add("NSEnabled", *b.boolean(False))
    cell_el = el.find("textFieldCell[@key='cell']")
    if cell_el is None:
        cell_el = el.find("secureTextFieldCell[@key='cell']")
    if cell_el is None:
        raise I.XibError(f"<textField> without textFieldCell ({where})")
    cell = _cell(b, cell_el, o, where, owner_id=cell_el.get("id"),
                 cell_cls="NSSecureTextFieldCell" if secure else "NSTextFieldCell",
                 id_map=id_map)
    locales = el.find("allowedInputSourceLocales")
    if locales is None:
        # probe AccountsFeedbin password cell: the element sits inside the
        # secureTextFieldCell there
        locales = cell_el.find("allowedInputSourceLocales")
    if locales is not None:
        # probe AccountsFeedbin [72]: array of the locale strings on the CELL
        larr = b.new("NSArray")
        larr.add("NSInlinedValue", *b.boolean(False))
        for s in locales.findall("string"):
            larr.add("UINibEncoderEmptyKey", *b.ref(b.string(s.text or "")))
        cell.add("NSAllowedInputLocales", *b.ref(larr))
    if el.get("textCompletion") == "NO":
        # probe AccountsAddCloudKit [59]: last cell key, bool false
        cell.add("NSAutomaticTextCompletionDisabled", *b.boolean(False))
    o.add("NSCell", *b.ref(cell))
    id_map[el.get("id") + "#cell"] = cell
    o.add("NSAllowsLogicalLayoutDirection",
          *b.boolean(not b.localize
                     and (el.get("horizontalHuggingPriority") is not None
                          or cell_el.get("scrollable") == "YES"
                          or (cell_el.get("selectable") == "YES"
                              and el.get("editable") is None))))
    if el.get("allowsExpansionToolTips"):
        # probe DinosaursWindow proto field [346]: attr archives INVERTED
        o.add("NSControlAllowsExpansionToolTips",
              *b.boolean(el.get("allowsExpansionToolTips") != "YES"))
    # probe GeneralPreferencesView [128]/[161]: controlSize=small -> view 1
    o.add("NSControlSize", *b.int8(1 if cell_el.get("controlSize") == "small" else 0))
    o.add("NSControlContinuous", *b.boolean(True))
    o.add("NSControlRefusesFirstResponder", *b.boolean(True))
    o.add("NSControlUsesSingleLineMode",
          *b.boolean(cell_el.get("usesSingleLineMode") != "YES"))
    align = cell_el.get("alignment", "natural")
    if align not in CONTROL_ALIGN:
        raise I.XibError(f"alignment {align!r} not probed ({where})")
    o.add("NSControlTextAlignment", *b.int8(CONTROL_ALIGN[align]))
    o.add("NSControlLineBreakMode", *b.int8(LINE_BREAK[lb_of(cell_el)]))
    o.add("NSControlWritingDirection", N.INT64, -1)
    o.add("NSControlSendActionMask", *b.int8(4))
    o.add("NSTextFieldAlignmentRectInsetsVersion", *b.int8(2))
    if getattr(b, "proto_mode", False):
        # prototypeCellView embedded nib compile (golden SidebarView proto60)
        o.add("NSTextFieldLineBreakStrategyVersion", *b.int8(2))
        o.add("NSLineBreakStrategy", *int_fit(65535))
    if el.get("contentType"):
        o.add("NSTextContentType", *b.ref(b.string(el.get("contentType"))))
    o.add("NSAllowsWritingTools", *b.boolean(secure))
    o.add("NSTextFieldAllowsWritingToolsAffordance", *b.boolean(True))
    o.add("NS.resolvesNaturalAlignmentWithBaseWritingDirection", *b.boolean(True))
    id_map[el.get("id")] = o
    cell = id_map[el.get("id") + "#cell"]
    pairs = [(o, parent), (cell, o)]
    fel = cell_el.find("numberFormatter[@key='formatter']")
    if fel is not None and fel.get("id") in id_map:
        pairs.append((id_map[fel.get("id")], cell))
    pairs.extend((con, o) for con in cons)
    return o, pairs


def lb_of(cell_el):
    lb = cell_el.get("lineBreakMode", "wordWrap")
    return lb



def _add_subview_elements(b, elements, o, where, id_map, guides, keys):
    """Build each subview (depth-first, cell included), reusing ones another
    branch already built; appends the subview to o's NSSubviews array."""
    arr = b.new("NSMutableArray")
    arr.add("NSInlinedValue", *b.boolean(False))
    o.add("NSSubviews", *b.ref(arr))
    for child in elements:
        existing = id_map.get(child.get("id"))
        if existing is not None:
            arr.add("UINibEncoderEmptyKey", *b.ref(existing))
            continue
        sub, sub_pairs = _build_element(b, child, where, superview=o,
                                        id_map=id_map, guides=guides, parent=o)
        arr.add("UINibEncoderEmptyKey", *b.ref(sub))
        keys.extend(sub_pairs)


def _view_frame(b, el, o, where, superview):
    if superview is not None:
        r = el.find("rect[@key='frame']")
        zero = r is not None and r.get("x", "0") in ("0", "0.0") and r.get("y", "0") in ("0", "0.0")
        o.add("NSFrameSize" if zero else "NSFrame",
              *b.ref(b.string(_size_str(el) if zero else _rect(el, "frame", where))))
        o.add("NSSuperview", *b.ref(superview))
        if el.get("wantsLayer") == "YES":
            o.add("NSViewIsLayerTreeHost", *b.boolean(False))
        return
    # ibtool archives the constraint-SOLVED canvas frame here; xibs whose
    # saved frames match the solved layout reproduce byte-for-byte, stale
    # ones differ in the frame strings only (loads identically: Auto Layout
    # re-fits at runtime).
    r = getattr(b, "cv_rect", None)
    if r is not None:
        cr = getattr(b, "cv_content_rect", None)
        rw, rh = float(r.get("width")), float(r.get("height"))
        if cr is None:
            o.add("NSFrameSize", *b.ref(b.string(_size_str(el))))
        elif (rw, rh) == cr:
            o.add("NSFrameSize", *b.ref(b.string(
                "{%s, %s}" % (_fmt_g(cr[0]), _fmt_g(cr[1])))))
        elif rw == cr[0]:
            # canvas with equal widths: frame shifted by the height delta
            o.add("NSFrame", *b.ref(b.string(
                "{{0, %s}, {%s, %s}}" % (_fmt_g(cr[1] - rh),
                                         _fmt_g(cr[0]), _fmt_g(rh)))))
        elif rh == cr[1]:
            o.add("NSFrameSize", *b.ref(b.string(
                "{%s, %s}" % (_fmt_g(rw), _fmt_g(cr[1])))))
        else:
            o.add("NSFrameSize", *b.ref(b.string(
                "{%s, %s}" % (_fmt_g(cr[0]), _fmt_g(cr[1])))))
    else:
        o.add("NSFrameSize", *b.ref(b.string(_size_str(el))))
    if el.get("wantsLayer") == "YES":
        o.add("NSViewIsLayerTreeHost", *b.boolean(False))


def _view_constraints_and_guides(b, el, o, where, id_map, guides, keys):
    """Constraints (probe-ordered), hugging/anti-compression priorities and
    the layout guides; appends constraint key pairs. Returns guide_kinds."""
    cons_el = el.find("constraints")
    cons = []
    gl = el.findall("viewLayoutGuide")
    guide_kinds = {}
    if gl:
        for g in gl:
            if g.get("key") not in GUIDE_IDENT:
                raise I.XibError(f"viewLayoutGuide {g.get('key')!r} not probed ({where})")
        guide_kinds.update({_guide_id(el, k): k for k in ("safeArea", "layoutMargins")})
    if cons_el is not None and cons_el.findall("constraint"):
        carr = b.new("NSArray")
        carr.add("NSInlinedValue", *b.boolean(False))
        els = I._constraint_order(el, cons_el.findall("constraint"), where, mac=True)
        for c in els:
            # a constraint already built as an outlet destination (probe TCV:
            # KCa allocated at connection time) is reused, not rebuilt
            cons.append(id_map[c.get("id")] if c.get("id") in id_map
                        else _constraint(b, c, o, el.get("id"), id_map, guides,
                                         guide_kinds, where))
        b.cons_order[el.get("id")] = [c.get("id") for c in els]
        for c in cons:
            carr.add("UINibEncoderEmptyKey", *b.ref(c))
        o.add("NSViewConstraints", *b.ref(carr))
        keys.extend((c, o) for c in cons)
    h = el.get("horizontalHuggingPriority")
    v2 = el.get("verticalHuggingPriority")
    if (h is not None and h != "250") or (v2 is not None and v2 != "750"):
        # probe GeneralPreferencesView root swapper: {1000, 1000} both keys,
        # between NSViewConstraints and the guide keys
        o.add("NSHuggingPriority",
              *b.ref(b.string("{%s, %s}" % (_fmt_g(h or 250), _fmt_g(v2 or 750)))))
    h = el.get("horizontalCompressionResistancePriority")
    v2 = el.get("verticalCompressionResistancePriority")
    if (h is not None and h != "750") or (v2 is not None and v2 != "750"):
        o.add("NSAntiCompressionPriority",
              *b.ref(b.string("{%s, %s}" % (_fmt_g(h or 750), _fmt_g(v2 or 750)))))
    if gl:
        larr = b.new("NSArray")
        larr.add("NSInlinedValue", *b.boolean(False))
        for kind in ("safeArea", "layoutMargins"):
            larr.add("UINibEncoderEmptyKey",
                     *b.ref(_guide(b, _guide_id(el, kind), guides, guide_kinds, where)))
        o.add("NSViewLayoutGuides", *b.ref(larr))
        for kind, key, t in (("safeArea", "IBNSSafeAreaLayoutGuide", 2),
                             ("layoutMargins", "IBNSLayoutMarginsGuide", 1)):
            g = b.new("IBNSViewAutolayoutGuide")
            g.add("IBNSLayoutGuideSystemType", *b.int8(t))
            o.add(key, *b.ref(g))
    else:
        o.add("IBNSSafeAreaLayoutGuide", *(N.NIL, None))
        o.add("IBNSLayoutMarginsGuide", *(N.NIL, None))
    o.add("IBNSClipsToBounds", *b.int8(0))
    return guide_kinds


def _stack_view_extras(b, el, o, where, subs):
    # probe AccountsAddLocal [55]/[57] (empty stacks), ShareViewController
    # [11] (arranged subviews + NSStackViewBeginningContainer)
    align = el.get("alignment")
    stack_align = {"bottom": 4, "centerY": 10, "firstBaseline": 12}.get(align)
    if stack_align is None:
        raise I.XibError(f"stackView alignment {align!r} not probed ({where})")
    if el.get("orientation") not in ("horizontal", "vertical"):
        raise I.XibError(f"stackView orientation {el.get('orientation')!r} "
                         f"not probed ({where})")
    if el.get("distribution", "fill") != "fill":
        raise I.XibError(f"stackView distribution "
                         f"{el.get('distribution')!r} not probed ({where})")
    o.add("NSStackViewOrientation",
          *b.int8(0 if el.get("orientation") == "horizontal" else 1))
    o.add("NSStackViewSecondaryAlignment",
          *b.int8({"centerY": 3, "bottom": 4, "firstBaseline": 2}[align]))
    o.add("NSStackViewAlignment", *b.int8(stack_align))
    o.add("NSStackViewVerticalClippingResistance", *b.float32(
        float(el.get("verticalCompressionResistancePriority", 1000))))
    o.add("NSStackViewHorizontalClippingResistance", *b.float32(
        float(el.get("horizontalCompressionResistancePriority", 1000))))
    o.add("NSStackViewVerticalHugging", *b.float32(
        float(el.get("verticalStackHuggingPriority", 250))))
    o.add("NSStackViewHorizontalHugging", *b.float32(
        float(el.get("horizontalStackHuggingPriority", 250))))
    o.add("NSStackViewSpacing", *b.float32(float(el.get("spacing", 8))))
    o.add("NSStackViewdistribution", *b.int8(0))
    for edge in ("top", "left", "right", "bottom"):
        o.add(f"NSStackViewEdgeInsets.{edge}", *b.float32(0.0))
    if subs is not None:
        # container allocated after the arranged subviews' subtrees and the
        # stack frame string (golden ShareVC [61] after [60])
        cont = b.new("NSStackViewContainer")
        cont.add("NSNextResponder", *(N.NIL, None))
        cont.add("NSNibTouchBar", *(N.NIL, None))
        cont.add("NSvFlags", *b.int16(256))
        cont.add("NSFrameSize", *b.ref(b.string("{0, 0}")))
        cont.add("NSViewWantsBestResolutionOpenGLSurface", *b.boolean(False))
        cont.add("NSDoNotTranslateAutoresizingMask", *b.boolean(False))
        cont.add("IBNSSafeAreaLayoutGuide", *(N.NIL, None))
        cont.add("IBNSLayoutMarginsGuide", *(N.NIL, None))
        cont.add("IBNSClipsToBounds", *b.int8(0))
        cont.add("NSStackViewContainerStackView", *b.ref(o))
        cont.add("NSStackViewContainerViewToCustomAfterSpaceMap", *(N.NIL, None))
        cont.add("NSStackViewContainerVisibilityPriorities", *(N.NIL, None))
        ndv = b.new("NSMutableArray")
        ndv.add("NSInlinedValue", *b.boolean(False))
        cont.add("NSStackViewContainerNonDroppedViews", *b.ref(ndv))
        for child in subs:
            ndv.add("UINibEncoderEmptyKey", *b.ref(id_map[child.get("id")]))
        o.add("NSStackViewBeginningContainer", *b.ref(cont))
    # probe: xib detachesHiddenViews="YES" archives False (inverted)
    o.add("NSStackViewDetachesHiddenViews",
          *b.boolean(el.get("detachesHiddenViews") != "YES"))
    o.add("NSStackViewHasFlatViewHierarchy", *b.boolean(False))


def _grid_view_extras(b, el, o, where, id_map):
    # probe AccountsFeedbin [106..128]: contents build as plain subviews
    # (gridCell doc order), then grid scaffolding after the frame
    XP = {"trailing": 3, "leading": 2}
    o.add("NSGrid_rowSpacing", *b.float64(float(el.get("rowSpacing", 0))))
    o.add("NSGrid_columnSpacing", *b.float64(float(el.get("columnSpacing", 0))))
    o.add("NSGrid_xPlacement", *b.int8(XP.get(el.get("xPlacement"), 0)))
    o.add("NSGrid_yPlacement", *b.int8({"center": 4}.get(el.get("yPlacement"), 0)))
    o.add("NSGrid_alignment", *b.int8({"none": 1}.get(el.get("rowAlignment"), 0)))
    FLT_MIN = 1.1754943508222875e-38
    cols = {c.get("id"): c for c in el.findall("columns/gridColumn")}
    rarr = b.new("NSMutableArray")
    rarr.add("NSInlinedValue", *b.boolean(False))
    o.add("NSGrid_rows", *b.ref(rarr))
    col_objs = {}
    row_objs = []
    cell_of = {}
    for r_el in el.findall("rows/gridRow"):
        row = b.new("NSGridRow")
        row_objs.append(row)
        rarr.add("UINibEncoderEmptyKey", *b.ref(row))
        row.add("NSGrid_owningGrid", *b.ref(o))
        row.add("NSGrid_yPlacement", *b.int8(0))
        row.add("NSGrid_alignment", *b.int8(0))
        row.add("NSGrid_height", *b.float64(FLT_MIN))
        row.add("NSGrid_topPadding", *b.float64(0.0))
        row.add("NSGrid_bottomPadding", *b.float64(0.0))
        row.add("NSGrid_hidden", *b.boolean(True))  # inverted: no attr -> True
        carr = b.new("NSMutableArray")
        carr.add("NSInlinedValue", *b.boolean(False))
        row.add("NSGrid_cells", *b.ref(carr))
        for c_el in el.findall(f"gridCells/gridCell[@row='{r_el.get('id')}']"):
            cell = b.new("NSGridCell")
            cell_of[c_el.get("id")] = cell
            carr.add("UINibEncoderEmptyKey", *b.ref(cell))
            cell.add("NSGrid_owningRow", *b.ref(row))
            col_id = c_el.get("column")
            if col_id not in col_objs:
                col_el = cols[col_id]
                col = b.new("NSGridColumn")
                col_objs[col_id] = col
                col.add("NSGrid_owningGrid", *b.ref(o))
                col.add("NSGrid_xPlacement", *b.int8(XP.get(col_el.get("xPlacement"), 0)))
                col.add("NSGrid_width", *b.float64(FLT_MIN))
                col.add("NSGrid_leadingPadding", *b.float64(0.0))
                col.add("NSGrid_trailingPadding", *b.float64(0.0))
                col.add("NSGrid_hidden", *b.boolean(True))
            cell.add("NSGrid_owningColumn", *b.ref(col_objs[col_id]))
            cell.add("NSGrid_mergeHead", *(N.NIL, None))
            cell.add("NSGrid_xPlacement", *b.int8(0))
            cell.add("NSGrid_yPlacement", *b.int8(0))
            cell.add("NSGrid_alignment", *b.int8(0))
            content_el = c_el.find("*[@key='contentView']")
            sub = id_map.get(content_el.get("id")) if content_el is not None else None
            if sub is None:
                raise I.XibError(f"<gridCell> without built contentView "
                                 f"{content_el.get('id')!r} ({where})")
            cell.add("NSGrid_content", *b.ref(sub))
    clarr = b.new("NSMutableArray")
    clarr.add("NSInlinedValue", *b.boolean(False))
    for c_el in el.findall("columns/gridColumn"):
        clarr.add("UINibEncoderEmptyKey", *b.ref(col_objs[c_el.get("id")]))
    o.add("NSGrid_columns", *b.ref(clarr))
    # _collect_keys emits the grid's key pairs (rows, columns, then per-cell
    # groups); it needs the scaffolding objects, which have no xib ids
    b.grid_meta[el.get("id")] = (
        row_objs,
        [col_objs[c.get("id")] for c in el.findall("columns/gridColumn")],
        cell_of)


def _view(b, el, where, superview=None, id_map=None, guides=None, parent=None,
          root=False):
    """<view>/<customView> -> NSView or NSClassSwapper; returns (obj, pairs).

    Allocation order is Apple's: the object, then subviews depth-first (each
    subview completes, cell included), then this view's frame, constraints
    (probe-ordered), layout guides, IB guide placeholders."""
    is_custom = el.tag == "customView" or el.get("customClass")
    o = b.new("NSStackView" if el.tag == "stackView"
              else "NSGridView" if el.tag == "gridView"
              else "NSClassSwapper" if is_custom else "NSView")
    if is_custom:
        # probe NNW3OpenPanelAccessoryView: bare <customView> (no customClass)
        # archives as NSClassSwapper with NSView/NSView; with customClass the
        # mangled name + NSView
        o.add("NSClassName", *b.ref(b.string(I._swift_class(el) or "NSView")))
        o.add("NSOriginalClassName", *b.ref(b.string("NSView")))
    o.add("NSNextResponder", *(b.ref(superview) if superview is not None else (N.NIL, None)))
    o.add("NSNibTouchBar", *(N.NIL, None))
    v, vt = _vflags(el, where)
    o.add("NSvFlags", vt, v)
    id_map[el.get("id")] = o
    keys = [(o, parent)]
    if el.tag == "gridView":
        # gridCell contentView elements are the subview source (probe
        # AccountsFeedbin [107]: doc order, grid is NSNextResponder)
        contents = []
        for c_el in el.findall("gridCells/gridCell"):
            content_el = c_el.find("*[@key='contentView']")
            if content_el is None:
                raise I.XibError(f"<gridCell> without contentView ({where})")
            contents.append(content_el)
        _add_subview_elements(b, contents, o, where, id_map, guides, keys)
        subs = None
    else:
        subs = el.find("subviews")
        if subs is not None:
            _add_subview_elements(b, subs, o, where, id_map, guides, keys)
    _view_frame(b, el, o, where, superview)
    if el.get("alphaValue") is not None:
        o.add("NSViewAlphaValue", *b.float64(float(el.get("alphaValue"))))
    o.add("NSViewWantsBestResolutionOpenGLSurface", *b.boolean(False))
    if superview is not None and _translates(el):
        o.add("NSDoNotTranslateAutoresizingMask", *b.boolean(False))
    _view_constraints_and_guides(b, el, o, where, id_map, guides, keys)
    if el.tag == "stackView":
        _stack_view_extras(b, el, o, where, subs)
    if el.tag == "gridView":
        _grid_view_extras(b, el, o, where, id_map)
    return o, keys


def _guide_id(el, kind):
    for g in el.findall("viewLayoutGuide"):
        if g.get("key") == kind:
            return g.get("id")
    return f"{el.get('id')}#{kind}"  # auto margins guide


def _size_str(el):
    r = el.find("rect[@key='frame']")
    if r is None:
        raise I.XibError(f"<{el.tag}> is missing frame rect")
    return "{%s, %s}" % (_fmt_g(r.get("width")), _fmt_g(r.get("height")))


def _table_cell_view(b, el, where, superview, id_map, parent=None, ident=None):
    """<tableCellView> prototype: NSTableCellView, swapper when customClass
    (probe golden SidebarCell: NSOriginalClassName NSTableCellView, no
    NSSuperview key, NSReuseIdentifierKey from the identifier)."""
    o = b.new("NSClassSwapper" if el.get("customClass") else "NSTableCellView")
    if el.get("customClass"):
        o.add("NSClassName", *b.ref(b.string(I._swift_class(el))))
        o.add("NSOriginalClassName", *b.ref(b.string("NSTableCellView")))
    id_map[el.get("id")] = o
    o.add("NSNextResponder", *(b.ref(superview) if superview is not None else (N.NIL, None)))
    o.add("NSNibTouchBar", *(N.NIL, None))
    v, vt = _vflags(el, where)
    o.add("NSvFlags", vt, v)
    keys = [(o, parent)]
    subs = el.find("subviews")
    if subs is not None:
        arr = b.new("NSMutableArray")
        arr.add("NSInlinedValue", *b.boolean(False))
        o.add("NSSubviews", *b.ref(arr))
        guides = {}
        for child in subs:
            sub, sub_pairs = _build_element(b, child, where, superview=o,
                                            id_map=id_map, guides=guides, parent=o)
            arr.add("UINibEncoderEmptyKey", *b.ref(sub))
            keys.extend(sub_pairs)
    # golden SidebarView [146]: the frame string lands after the subtree
    r = el.find("rect[@key='frame']")
    if float(r.get("x", 0)) == 0 and float(r.get("y", 0)) == 0:
        o.add("NSFrameSize", *b.ref(b.string(_size_str(el))))
    else:
        o.add("NSFrame", *b.ref(b.string(_rect(el, "frame", where))))
    o.add("NSViewWantsBestResolutionOpenGLSurface", *b.boolean(False))
    ident_attr = el.get("identifier") or ident
    if ident_attr:
        # embedded reusables fall back to the column identifier (probe
        # DinosaursWindow 'account' proto: cell element has no identifier)
        o.add("NSReuseIdentifierKey", *b.ref(b.string(ident_attr)))
    cons_el = el.find("constraints")
    if cons_el is not None and cons_el.findall("constraint"):
        # golden CurrentActivity [179]: NSViewConstraints after
        # NSReuseIdentifierKey, before the IB guide placeholders
        carr = b.new("NSArray")
        carr.add("NSInlinedValue", *b.boolean(False))
        els = I._constraint_order(el, cons_el.findall("constraint"), where, mac=True)
        cons = [id_map[c.get("id")] if c.get("id") in id_map
                else _constraint(b, c, o, el.get("id"), id_map, {}, {}, where)
                for c in els]
        b.cons_order[el.get("id")] = [c.get("id") for c in els]
        for con in cons:
            carr.add("UINibEncoderEmptyKey", *b.ref(con))
        o.add("NSViewConstraints", *b.ref(carr))
        keys.extend((con, o) for con in cons)
    o.add("IBNSSafeAreaLayoutGuide", *(N.NIL, None))
    o.add("IBNSLayoutMarginsGuide", *(N.NIL, None))
    o.add("IBNSClipsToBounds", *b.int8(0))
    return o, keys


def _visual_effect_view(b, el, where, superview, id_map, parent=None):
    """<visualEffectView> (probe CurrentActivity [102] / AccountStats [169]):
    NSView-like shell + NSVisualEffectViewBlendingMode/State; the material
    attribute is NOT archived."""
    o = b.new("NSVisualEffectView")
    o.add("NSNextResponder", *(b.ref(superview) if superview is not None else (N.NIL, None)))
    o.add("NSNibTouchBar", *(N.NIL, None))
    v, vt = _vflags(el, where)
    o.add("NSvFlags", vt, v)
    id_map[el.get("id")] = o
    keys = [(o, parent)]
    subs = el.find("subviews")
    if subs is not None:
        arr = b.new("NSMutableArray")
        arr.add("NSInlinedValue", *b.boolean(False))
        o.add("NSSubviews", *b.ref(arr))
        for child in subs:
            existing = id_map.get(child.get("id"))
            if existing is not None:
                arr.add("UINibEncoderEmptyKey", *b.ref(existing))
                continue
            sub, sub_pairs = _build_element(b, child, where, superview=o,
                                            id_map=id_map, guides={}, parent=o)
            arr.add("UINibEncoderEmptyKey", *b.ref(sub))
            keys.extend(sub_pairs)
    r = el.find("rect[@key='frame']")
    zero = r is None or (r.get("x", "0") in ("0", "0.0") and r.get("y", "0") in ("0", "0.0"))
    o.add("NSFrameSize" if zero else "NSFrame", *b.ref(b.string(
        _size_str(el) if zero else _rect(el, "frame", where))))
    if superview is not None:
        o.add("NSSuperview", *b.ref(superview))
    if el.get("wantsLayer") == "YES":
        o.add("NSViewIsLayerTreeHost", *b.boolean(False))
    o.add("NSViewWantsBestResolutionOpenGLSurface", *b.boolean(False))
    if _translates(el):
        o.add("NSDoNotTranslateAutoresizingMask", *b.boolean(False))
    cons_el = el.find("constraints")
    if cons_el is not None and cons_el.findall("constraint"):
        carr = b.new("NSArray")
        carr.add("NSInlinedValue", *b.boolean(False))
        els = I._constraint_order(el, cons_el.findall("constraint"), where, mac=True)
        cons = [id_map[c.get("id")] if c.get("id") in id_map
                else _constraint(b, c, o, el.get("id"), id_map, {}, {}, where)
                for c in els]
        b.cons_order[el.get("id")] = [c.get("id") for c in els]
        for con in cons:
            carr.add("UINibEncoderEmptyKey", *b.ref(con))
        o.add("NSViewConstraints", *b.ref(carr))
        keys.extend((con, o) for con in cons)
    o.add("IBNSSafeAreaLayoutGuide", *(N.NIL, None))
    o.add("IBNSLayoutMarginsGuide", *(N.NIL, None))
    o.add("IBNSClipsToBounds", *b.int8(0))
    blending = {"behindWindow": 0, "withinWindow": 1}.get(el.get("blendingMode"))
    if blending is None:
        raise I.XibError(f"visualEffectView blendingMode {el.get('blendingMode')!r} "
                         f"not probed ({where})")
    o.add("NSVisualEffectViewBlendingMode", *b.int8(blending))
    state = {"followsWindowActiveState": 0, "active": 1, "inactive": 2}.get(el.get("state"))
    if state is not None:
        o.add("NSVisualEffectViewState", *b.int8(state))
    o.add("NSVisualEffectViewMaskImage", *(N.NIL, None))
    material = {"titlebar": 3, "menu": 4, "headerView": 5, "sheet": 6,
                "windowBackground": 7, "hudWindow": 8, "fullScreenUI": 9,
                "popover": 10, "sidebar": 11, "mediumLight": 12,
                "underPageBackground": 13}.get(el.get("material"))
    if material is None:
        raise I.XibError(f"visualEffectView material {el.get('material')!r} "
                         f"not probed ({where})")
    o.add("NSVisualEffectViewMaterial", *b.int8(material))
    o.add("IBVisualEffectViewExternalMaterial", *b.int8(material))
    o.add("IBVisualEffectViewAppearanceType", *b.int8(0))
    return o, keys


def _build_element(b, el, where, superview, id_map, guides, parent=None, root=False):
    """One element: (obj, [(obj, parent)] pairs for NSObjectsKeys/Values)."""
    if el.tag == "textField":
        return _field(b, el, where, superview, id_map, parent=parent)
    if el.tag in ("view", "customView", "stackView", "gridView"):
        return _view(b, el, where, superview=superview, id_map=id_map,
                     guides=guides, parent=parent, root=root)
    if el.tag == "secureTextField":
        return _field(b, el, where, superview, id_map, parent=parent)
    if el.tag == "button":
        return _button(b, el, where, superview, id_map, parent=parent)
    if el.tag == "stepper":
        return _stepper(b, el, where, superview, id_map, parent=parent)
    if el.tag == "popUpButton":
        return _popup(b, el, where, superview, id_map, parent=parent)
    if el.tag == "imageView":
        return _image_view(b, el, where, superview, id_map, parent=parent)
    if el.tag == "scrollView":
        return _scroll_view(b, el, where, superview, id_map, parent=parent)
    if el.tag in ("tableView", "outlineView"):
        return _table_view(b, el, where, superview, id_map, parent=parent)
    if el.tag == "tableCellView":
        return _table_cell_view(b, el, where, superview, id_map, parent=parent)
    if el.tag == "box":
        return _box(b, el, where, superview, id_map, parent=parent)
    if el.tag == "progressIndicator":
        return _progress_indicator(b, el, where, superview, id_map, parent=parent)
    if el.tag == "visualEffectView":
        return _visual_effect_view(b, el, where, superview, id_map, parent=parent)
    if el.tag == "textView":
        o = _text_view(b, el, where, superview)
        id_map[el.get("id")] = o
        return o, [(o, parent)]
    if el.tag == "window":
        return _window(b, el, where, id_map, parent=parent)
    raise I.XibError(f"unsupported element <{el.tag}> ({where})")


def _window(b, el, where, id_map, parent=None, obj=None):
    """<window> -> NSWindowTemplate with the probed key order.

    obj is pre-allocated for a visible-at-launch window: the canvas inlines
    the whole content tree right after the window head (probe About), with the
    window in NSVisibleWindows and the trailing keys after the tree."""
    o = obj if obj is not None else b.new("NSWindowTemplate")
    mask = el.find("windowStyleMask[@key='styleMask']")
    style = 0
    if mask is not None:
        for name, bit in STYLE_MASK.items():
            if mask.get(name) == "YES":
                style |= bit
    o.add("NSWindowStyleMask", *b.int_fit32(style))
    if mask is not None and mask.get("resizable") == "YES" and mask.get("titled") != "YES":
        o.add("NSWindowAllowNontitledResizable", *b.boolean(True))
    o.add("NSWindowBacking", *b.int8(2))
    o.add("NSWindowRect", *b.ref(b.string(_window_rect(el, where))))
    flags = 0x60000000
    if el.get("hidesOnDeactivate") == "YES":
        flags |= 0x80000000
    pos = el.find("windowPositionMask[@key='initialPositionMask']")
    if pos is not None:
        for name, bit in STRUTS.items():
            if pos.get(name) == "YES":
                flags |= bit
    else:
        flags |= sum(STRUTS.values())
    if flags > 0x7FFFFFFF:
        o.add("NSWTFlags", N.INT64, flags - 0x100000000)
    else:
        o.add("NSWTFlags", N.INT32, flags)
    o.add("NSWindowTitle", *b.ref(_localizable(b, el.get("id") or "",
                                               el.get("title", ""), where)))
    o.add("NSWindowSubtitle", *b.ref(b.string(el.get("subtitle", ""))))
    o.add("NSWindowClass", *b.ref(b.string(el.get("customClass", "NSWindow"))))
    o.add("NSViewClass", *(N.NIL, None))
    ident = el.get("identifier")
    o.add("NSUserInterfaceItemIdentifier",
          *(b.ref(b.string(ident)) if ident else (N.NIL, None)))
    min_sz = max_sz = None
    for v in el.findall("value"):
        if v.get("key") == "minSize":
            min_sz = _size(el, "minSize", where)
        elif v.get("key") == "maxSize":
            max_sz = _size(el, "maxSize", where)
    if max_sz is not None:
        o.add("NSWindowContentMaxSize", *b.ref(b.string(max_sz)))
    if min_sz is not None:
        o.add("NSWindowContentMinSize", *b.ref(b.string(min_sz)))
    cv = el.find("view[@key='contentView']")
    cv_pairs = []
    if cv is not None:
        if obj is not None:
            cv_obj, cv_pairs = _window_content(b, el, cv, o, where, id_map)
            o.add("NSWindowView", *b.ref(cv_obj))
    else:
        b.cv_rect = None
        o.add("NSWindowView", *(N.NIL, None))
    if cv is not None and obj is None:
        cv_obj, cv_pairs = _window_content(b, el, cv, o, where, id_map)
        o.add("NSWindowView", *b.ref(cv_obj))
    o.add("NSScreenRect", *b.ref(b.string(_rect(el, "screenRect", where))))
    if min_sz is not None:
        # content min/max plus the title bar: +24 for NSPanels (probe
        # InspectorWindow 256+24), +32 for regular windows (probe
        # CurrentActivity 200+32 / AccountStats 256+32)
        delta = 24 if el.get("customClass") == "NSPanel" else 32
        w, h = min_sz.strip("{}").split(", ")
        o.add("NSMinSize", *b.ref(b.string("{%s, %s}" % (w, _fmt_g(float(h) + delta)))))
    o.add("NSMaxSize", *b.ref(b.string(
        max_sz and "{%s, %s}" % (max_sz.strip("{}").split(", ")[0],
                                 _fmt_g(float(max_sz.strip("{}").split(", ")[1]) + 24))
        or "{10000000000000, 10000000000000}")))
    if el.get("frameAutosaveName") is not None:
        o.add("NSFrameAutosaveName", *b.ref(b.string(el.get("frameAutosaveName"))))
    coll = el.find("windowCollectionBehavior[@key='collectionBehavior']")
    if coll is not None:
        bits = 0
        for name, bit in COLLECTION_BEHAVIOR.items():
            if coll.get(name) == "YES":
                bits |= bit
        o.add("NSWindowCollectionBehavior", N.INT16, bits)
    o.add("NSWindowIsRestorable", *b.boolean(el.get("restorable") == "NO"))
    o.add("NSMinFullScreenContentSize", *b.ref(b.string("{0, 0}")))
    o.add("NSMaxFullScreenContentSize", *b.ref(b.string("{0, 0}")))
    if el.get("titleVisibility"):
        if el.get("titleVisibility") != "hidden":
            raise I.XibError(f"titleVisibility {el.get('titleVisibility')!r} not probed ({where})")
        o.add("NSWindowTitleVisibility", *b.int8(1))
    if el.get("titlebarAppearsTransparent"):
        if el.get("titlebarAppearsTransparent") != "YES":
            raise I.XibError(f"titlebarAppearsTransparent "
                             f"{el.get('titlebarAppearsTransparent')!r} not probed ({where})")
        o.add("NSTitlebarAppearsTransparent", *b.boolean(False))
    if el.get("separatorStyle"):
        if el.get("separatorStyle") != "none":
            raise I.XibError(f"separatorStyle {el.get('separatorStyle')!r} not probed ({where})")
        o.add("NSTitlebarSeparatorStyle", *b.int8(1))
    if el.get("tabbingMode"):
        if el.get("tabbingMode") not in TABBING_MODE:
            raise I.XibError(f"tabbingMode {el.get('tabbingMode')!r} not probed ({where})")
        o.add("NSWindowTabbingMode", *b.int8(TABBING_MODE[el.get("tabbingMode")]))
    if el.get("toolbarStyle"):
        if el.get("toolbarStyle") not in TOOLBAR_STYLE:
            raise I.XibError(f"toolbarStyle {el.get('toolbarStyle')!r} not probed ({where})")
        o.add("NSWindowToolbarStyle", *b.int8(TOOLBAR_STYLE[el.get("toolbarStyle")]))
    if el.get("customClass"):
        o.add("IBClassReference", *b.ref(_classref(b, el.get("customClass"), None, None)))
    id_map[el.get("id")] = o
    return o, [(o, parent)] + cv_pairs


def _window_content(b, el, cv, o, where, id_map):
    """Build the contentView inline; returns (obj, pairs)."""
    b.cv_rect = cv.find("rect[@key='frame']")
    cr = el.find("rect[@key='contentRect']")
    b.cv_content_rect = (float(cr.get("width")), float(cr.get("height"))) if cr is not None else None
    b.cv_wants_layer = cv.get("wantsLayer") == "YES"
    cv_obj, pairs = _build_element(b, cv, where, superview=None,
                                   id_map=id_map, guides={}, parent=o)
    b.cv_rect = None
    return cv_obj, pairs


def _conn_blocks(objects_el):
    """(source element, <outlet>/<action>) pairs in document pre-order."""
    pairs = []

    def walk(el):
        for c in el.findall("connections"):
            for conn in c:
                pairs.append((el, conn))
        for tag in ("buttonCell", "popUpButtonCell"):
            for cell in el.findall(f"{tag}[@key='cell']"):
                walk(cell)
                for menu in cell.findall("menu[@key='menu']"):
                    walk_menu(menu)
        cv = el.find("view[@key='contentView']")
        if cv is not None:
            walk(cv)
        clip = el.find("clipView[@key='contentView']")
        if clip is not None:
            walk(clip)
        subs = el.find("subviews")
        if subs is not None:
            for child in subs:
                walk(child)
        for pv in el.findall("prototypeCellViews/tableCellView"):
            walk(pv)
        for col in el.findall("tableColumns/tableColumn"):
            for pv in col.findall("prototypeCellViews/tableCellView"):
                walk(pv)

    def walk_menu(el):
        for c in el.findall("connections"):
            for conn in c:
                pairs.append((el, conn))
        items = el.find("items")
        if items is not None:
            for it in items:
                walk_menu(it)
        sub = el.find("menu[@key='submenu']")
        if sub is not None:
            walk_menu(sub)

    for el in objects_el:
        if el.tag == "menu":
            walk_menu(el)
        elif el.tag in ("customObject", "window", "customView", "view",
                        "scrollView", "tableView", "outlineView"):
            walk(el)
    return pairs


def _find_id(root, ident):
    return root.find(f".//*[@id='{ident}']")


def _find_parent(root, ident):
    """The element whose subviews hold ident (ElementTree has no parent pointers)."""
    for el in root.iter():
        subs = el.find("subviews")
        if subs is not None and any(c.get("id") == ident for c in subs):
            return el
    # gridCell contentView elements (probe AccountsFeedbin: the field's
    # superview is the gridView, not the gridCell); the content carries
    # key="contentView" (it may be the field element itself)
    for gc in root.iter("gridCell"):
        cv = gc.find("*[@key='contentView']")
        if cv is not None and cv.get("id") == ident:
            return gc
    return None


def _xib_parse(path):
    """Parse and validate a macOS xib; returns (doc, objects, where)."""
    tree = ET.parse(path)
    doc = tree.getroot()
    if doc.get("targetRuntime") != "MacOSX.Cocoa":
        raise I.XibError(f"{path}: targetRuntime {doc.get('targetRuntime')!r} is not MacOSX.Cocoa")
    objects = doc.find("objects")
    if objects is None:
        raise I.XibError(f"{path}: no <objects> element")
    return doc, objects, os.path.basename(path)


def _xib_resources(b, res):
    for img in res.findall("image"):
        b.image_decls[img.get("name")] = img
    for nc in res.findall("namedColor"):
        b.named_color_els[nc.get("name")] = nc.find("color")


def _xib_owner(b, objects, path, where):
    owner_el = next((e for e in objects if e.get("id") == "-2"), None)
    if owner_el is None:
        raise I.XibError(f"{path}: no File's Owner (id=-2)")
    if not owner_el.get("customClass"):
        raise I.XibError(f"{path}: File's Owner without customClass ({where})")
    return _custom_object(b, owner_el, I._swift_class(owner_el), where)


def _xib_visible_windows(b, objects, where, id_map, owner, vis):
    """Windows without visibleAtLaunch="NO" are built up front, before the
    connections array (probe About: set -> window template with the full
    content tree inlined -> trailing window keys -> connections last).
    Returns (keys, vis_ids)."""
    keys = []
    vis_ids = set()
    for w_el in objects:
        if w_el.tag == "window" and w_el.get("visibleAtLaunch") != "NO":
            o = b.new("NSWindowTemplate")
            vis.add("UINibEncoderEmptyKey", *b.ref(o))
            _wobj, wkeys = _window(b, w_el, where, id_map, parent=owner, obj=o)
            keys.extend(wkeys)
            vis_ids.add(w_el.get("id"))
    return keys, vis_ids


def _xib_stackview_connector(b, objects, where, id_map, conns_arr, conn_objs,
                             late_pending):
    """A stackView with arranged subviews emits an early-decode NSNibConnector
    as the FIRST connection; its source (the stack view, with its whole
    subtree) allocates right after the connector, before everything else
    (probe ShareViewController [10]/[11])."""
    sv_el = next((e for e in objects.iter("stackView")
                  if (s := e.find("subviews")) is not None and len(s)), None)
    if sv_el is None:
        return
    early = b.new("NSNibConnector")
    sup = _Late()
    sv = _build_element(b, sv_el, where, superview=sup, id_map=id_map,
                        guides={}, parent=sup)[0]
    early.add("NSSource", *b.ref(sv))
    early.add("NSLabel", *b.ref(b.string(
        "Encoding NSStackView requires being decoded before other "
        "connections with an early decoding order priority of 999990.")))
    conns_arr.add("UINibEncoderEmptyKey", *b.ref(early))
    conn_objs.append(early)
    late_pending.append((sup, _find_parent(objects, sv_el.get("id")).get("id")))


def _xib_lazy_destination(b, objects, owner, where, id_map, late_pending,
                          late_menus, el, dest_id):
    """Build a connection destination before the tree walk reaches it, in the
    order Apple's ibtool allocates (probe MainMenu [8], TimelineContainerView
    [17], NothingInspector)."""
    if el.tag == "menu":
        _xib_menu(b, el, id_map, where)
    elif el.tag == "menuItem":
        parent_el = _menu_parent_el(objects, dest_id)
        if parent_el is None:
            raise I.XibError(f"menu item {dest_id!r} has no parent menu ({where})")
        late = _Late()
        _xib_menu_item(b, el, late, id_map, where)
        late_menus.append((late, parent_el.get("id")))
    elif el.tag == "customObject":
        # probe MainMenu [8]: customObject with customModule -> swapper
        id_map[dest_id] = _xib_swapper(b, el, where)
    elif el.tag == "constraint":
        # probe TimelineContainerView [17]: the constraint is allocated
        # at connection time; its not-yet-built items build RIGHT HERE
        # (golden box [18] + closure directly after constraint [17],
        # before the connector's label string [36])
        lates = []
        id_map[dest_id] = _constraint(b, el, owner, "-2", id_map, {},
                                      {}, where, lates=lates)
        for late, item_id in lates:
            item_el = _find_id(objects, item_id)
            if item_el is None or item_el.get("id") in id_map:
                continue
            parent_el = _find_parent(objects, item_id)
            sup = _Late()
            _build_element(b, item_el, where, superview=sup,
                           id_map=id_map, guides={}, parent=sup)
            late_pending.append((sup, parent_el.get("id")))
            late.obj = id_map[item_id]
    elif el.tag in ("window", "view", "customView", "textField",
                    "secureTextField", "gridView",
                    "button", "popUpButton", "imageView", "box",
                    "scrollView", "textView", "tableView",
                    "outlineView", "tableCellView", "progressIndicator"):
        parent_el = _find_parent(objects, dest_id)
        if parent_el is not None and parent_el.tag == "gridCell":
            # a gridCell content's superview is the gridView
            parent_el = next((gv for gv in objects.iter("gridView")
                              if any(gc.get("id") == parent_el.get("id")
                                     for gc in gv.findall("gridCells/gridCell"))),
                             None)
        is_cv = any(w.find("view[@key='contentView']") is not None
                    and w.find("view[@key='contentView']").get("id") == dest_id
                    for w in objects.findall("window"))
        if parent_el is not None:
            # A subview built by an outlet before its superview: Apple keeps
            # the superview as a forward reference (probe NothingInspector).
            late = _Late()
            _build_element(b, el, where, superview=late,
                           id_map=id_map, guides={}, parent=late)
            late_pending.append((late, parent_el.get("id")))
        elif is_cv:
            _build_element(b, el, where, superview=None,
                           id_map=id_map, guides={}, parent=owner)
        else:
            _build_element(b, el, where, superview=None,
                           id_map=id_map, guides={}, parent=owner, root=True)
    else:
        raise I.XibError(f"connection destination {dest_id!r} not found ({where})")


def _xib_outlet_connector(b, objects, owner, where, id_map, conn_objs,
                          conns_arr, late_pending, late_menus, src_el, conn_el):
    c = b.new("NSNibOutletConnector")
    src = id_map.get(src_el.get("id"))
    if src is None and src_el.tag == "tableCellView":
        # a prototype cell view referenced by its own outlet before the
        # tree walk builds it (probe SidebarView HeaderCell textField)
        src = _build_element(b, src_el, where, superview=None,
                             id_map=id_map, guides={}, parent=None)[0]
    if src is None and src_el.tag == "menu":
        src = _xib_menu(b, src_el, id_map, where)
    if src is None:
        raise I.XibError(f"connection source {src_el.get('id')!r} not built ({where})")
    c.add("NSSource", *b.ref(src))
    dest_id = conn_el.get("destination")
    if dest_id not in id_map:
        el = _find_id(objects, dest_id)
        if el is None:
            raise I.XibError(f"connection destination {dest_id!r} not found ({where})")
        _xib_lazy_destination(b, objects, owner, where, id_map, late_pending,
                              late_menus, el, dest_id)
    c.add("NSDestination", *b.ref(id_map[dest_id]))
    c.add("NSLabel", *b.ref(b.string(conn_el.get("property"))))
    c.add("NSChildControllerCreationSelectorName", *(N.NIL, None))
    conns_arr.add("UINibEncoderEmptyKey", *b.ref(c))
    conn_objs.append(c)


def _xib_action_connector(b, objects, where, id_map, conn_objs, conns_arr,
                          late_menus, src_el, conn_el):
    c = b.new("NSNibControlConnector")
    src = id_map.get(src_el.get("id"))
    if src is None:
        parent_el = _menu_parent_el(objects, src_el.get("id"))
        if parent_el is None:
            raise I.XibError(f"action source {src_el.get('id')!r} not built ({where})")
        late = _Late()
        src = _xib_menu_item(b, src_el, late, id_map, where)
        late_menus.append((late, parent_el.get("id")))
    c.add("NSSource", *b.ref(src))
    tgt = conn_el.get("target")
    if tgt is not None and tgt != "-1":
        if tgt not in id_map:
            raise I.XibError(f"action target {tgt!r} not built ({where})")
        c.add("NSDestination", *b.ref(id_map[tgt]))
    c.add("NSLabel", *b.ref(b.string(conn_el.get("selector"))))
    conns_arr.add("UINibEncoderEmptyKey", *b.ref(c))
    conn_objs.append(c)


def _xib_binding_options(b, opts, where, d):
    for o_el in opts:
        d.add("UINibEncoderEmptyKey", *b.ref(b.string(o_el.get("key"))))
        # bool values archive INVERTED (probe: value="NO" -> NS.boolval
        # TRUE); integers int_fit; strings plain
        if o_el.tag == "bool":
            key = ("boolval", o_el.get("value"))
            n = b.bool_nums.get(key)
            if n is None:
                n = b.new("NSNumber")
                n.add("NS.boolval",
                      N.TRUE if o_el.get("value") != "YES" else N.FALSE, None)
                b.bool_nums[key] = n
            d.add("UINibEncoderEmptyKey", *b.ref(n))
        elif o_el.tag == "integer":
            v = int(o_el.get("value"))
            n = b.number(N.INT8 if -128 <= v <= 127 else N.INT32, v)
            d.add("UINibEncoderEmptyKey", *b.ref(n))
        elif o_el.tag == "string":
            d.add("UINibEncoderEmptyKey", *b.ref(b.string(o_el.text or "")))
        else:
            raise I.XibError(f"binding option <{o_el.tag}> not probed ({where})")


def _xib_binding_connector(b, objects, owner, where, id_map, src_el, conn_el):
    """One NSNibBindingConnector; lazily builds a destination
    userDefaultsController with NSSharedInstance False (representsSharedInstance
    =YES archives False, probe CrashReporter [131]); its keys pair is
    (controller, owner). Returns (connector, key_pair_or_None)."""
    c = b.new("NSNibBindingConnector")
    src = id_map.get(src_el.get("id"))
    if src is None:
        raise I.XibError(f"binding source {src_el.get('id')!r} not built ({where})")
    c.add("NSSource", *b.ref(src))
    dest_id = conn_el.get("destination")
    key_pair = None
    if dest_id not in id_map:
        el = _find_id(objects, dest_id)
        if el is None or el.tag != "userDefaultsController":
            raise I.XibError(f"binding destination {dest_id!r} not found ({where})")
        udc = b.new("NSUserDefaultsController")
        # representsSharedInstance=YES -> NSSharedInstance false (inverted,
        # GP [311]/Crash [131]); bare element -> NSAppliesImmediately
        # (attr value, corpus point false; Adv golden [155]/[170])
        if el.get("representsSharedInstance") == "YES":
            udc.add("NSSharedInstance", *b.boolean(False))
        else:
            udc.add("NSAppliesImmediately",
                    *b.boolean(el.get("appliesImmediately") == "YES"))
        id_map[dest_id] = udc
        key_pair = (udc, owner)
    c.add("NSDestination", *b.ref(id_map[dest_id]))
    name, kp = conn_el.get("name"), conn_el.get("keyPath")
    c.add("NSLabel", *b.ref(b.string(f"{name}: {kp}")))
    c.add("NSBinding", *b.ref(b.string(name)))
    c.add("NSKeyPath", *b.ref(b.string(kp)))
    opts = conn_el.find("dictionary[@key='options']")
    # probe GeneralPreferences golden [309] (QZ4-W8-rPi, no options el):
    # connectors without <dictionary key="options"> drop NSOptions and
    # allocate no dict
    if opts is not None:
        d = b.new("NSDictionary")
        d.add("NSInlinedValue", *b.boolean(False))
        c.add("NSOptions", *b.ref(d))
        _xib_binding_options(b, opts, where, d)
    c.add("NSNibBindingConnectorVersion", *b.int8(2))
    return c, key_pair


def _collect_grid_keys(b, el, obj, id_map, keys):
    # golden AccountsReaderAPI [221]: rows doc order, columns doc
    # order (parent = grid), then per gridCell doc order: cell ->
    # grid, content field -> cell, field cell -> field, field's
    # constraints -> field
    rows, cols, cell_of = b.grid_meta.get(el.get("id"), ([], [], {}))
    for r in rows:
        keys.append((r, obj))
    for c in cols:
        keys.append((c, obj))
    for c_el in el.findall("gridCells/gridCell"):
        cell = cell_of.get(c_el.get("id"))
        content_el = c_el.find("*[@key='contentView']")
        if cell is None or content_el is None:
            continue
        keys.append((cell, obj))
        fobj = id_map.get(content_el.get("id"))
        if fobj is None:
            continue
        keys.append((fobj, cell))
        fcell_el = content_el.find("*[@key='cell']")
        ckey = content_el.get("id") + "#cell"
        if fcell_el is not None and ckey in id_map:
            keys.append((id_map[ckey], fobj))
        for cid in b.cons_order.get(content_el.get("id"), []):
            if cid in id_map:
                keys.append((id_map[cid], fobj))


def _collect_table_keys(b, el, obj, id_map, keys, where):
    cols = el.find("tableColumns")
    for col_el in (cols if cols is not None else []):
        cobj = id_map.get(col_el.get("id"))
        if cobj is None:
            continue
        keys.append((cobj, obj))
        dc_el = col_el.find("textFieldCell[@key='dataCell']")
        if dc_el is not None and dc_el.get("id") in id_map:
            keys.append((id_map[dc_el.get("id")], cobj))
        pvs = col_el.find("prototypeCellViews")
        for pv in (pvs if pvs is not None else []):
            pobj = id_map.get(pv.get("id"))
            if pobj is None:
                pobj = _build_element(b, pv, where, superview=None,
                                      id_map=id_map, guides={},
                                      parent=cobj)[0]
            keys.append((pobj, cobj))
            subs3 = pv.find("subviews")
            if subs3 is not None:
                for child in subs3:
                    _collect_keys(b, child, pobj, id_map, keys, where)
            for cid in b.cons_order.get(pv.get("id"), []):
                if cid in id_map:
                    keys.append((id_map[cid], pobj))


def _collect_scroll_keys(b, el, obj, id_map, keys, where):
    clip = el.find("clipView[@key='contentView']")
    if clip is not None:
        cobj = id_map.get(clip.get("id"))
        if cobj is not None:
            keys.append((cobj, obj))
            subs2 = clip.find("subviews")
            if subs2 is not None:
                for child in subs2:
                    _collect_keys(b, child, cobj, id_map, keys, where)
    for k2 in ("horizontalScroller", "verticalScroller"):
        s_el = el.find(f"scroller[@key='{k2}']")
        if s_el is not None and s_el.get("id") in id_map:
            keys.append((id_map[s_el.get("id")], obj))
    subs2 = clip.find("subviews") if clip is not None else None
    if subs2 is not None and len(subs2) == 1 \
            and subs2[0].tag in ("tableView", "outlineView"):
        hv = subs2[0].find("tableHeaderView[@key='headerView']")
        if hv is not None and hv.get("id") in id_map:
            keys.append((id_map[hv.get("id")], obj))


def _collect_keys(b, el, parent, id_map, keys, where):
    """NSObjectsKeys follows document pre-order (probe
    DetailView/NothingInspector), not the lazy build order: window/contentView
    or view, cell after its control, subviews, then the view's constraints;
    the parent array mirrors it."""
    obj = id_map.get(el.get("id"))
    if obj is None:
        return
    keys.append((obj, parent))
    if el.tag == "gridView":
        _collect_grid_keys(b, el, obj, id_map, keys)
    if el.tag in ("textField", "button"):
        keys.append((id_map[el.get("id") + "#cell"], obj))
    if el.tag == "popUpButton":
        cell_el = el.find("popUpButtonCell[@key='cell']")
        menu_el = cell_el.find("menu[@key='menu']")
        # cell -> popup, menu -> cell, items -> menu (probe ImportOPMLSheet)
        keys.append((id_map[el.get("id") + "#cell"], obj))
        keys.append((id_map[menu_el.get("id")], id_map[cell_el.get("id")]))
        for m in menu_el.find("items"):
            keys.append((id_map[m.get("id")], id_map[menu_el.get("id")]))
    cv = el.find("view[@key='contentView']")
    if cv is not None:
        _collect_keys(b, cv, obj, id_map, keys, where)
    if el.tag in ("tableView", "outlineView"):
        _collect_table_keys(b, el, obj, id_map, keys, where)
    if el.tag == "scrollView":
        _collect_scroll_keys(b, el, obj, id_map, keys, where)
    subs = el.find("subviews")
    if subs is not None:
        for child in subs:
            _collect_keys(b, child, obj, id_map, keys, where)
    if el.tag in ("imageView",):
        if el.get("id") + "#cell" in id_map:
            keys.append((id_map[el.get("id") + "#cell"], obj))
    for cid in b.cons_order.get(el.get("id"), []):
        if cid in id_map:
            keys.append((id_map[cid], obj))


def _collect_menu_keys(b, el, parent, id_map, keys, where):
    mo = id_map.get(el.get("id"))
    if mo is None:
        mo = _xib_menu(b, el, id_map, where)
    keys.append((mo, parent))
    items = el.find("items")
    if items is not None:
        for it in items:
            io = id_map.get(it.get("id"))
            if io is None:
                io = _xib_menu_item(b, it, mo, id_map, where)
            keys.append((io, mo))
            sub = it.find("menu[@key='submenu']")
            if sub is not None:
                _collect_menu_keys(b, sub, io, id_map, keys, where)


def _xib_app_proxy(b, objects, path, where):
    app_el = next((e for e in objects if e.get("id") == "-3"), None)
    if app_el is None:
        raise I.XibError(f"{path}: no Application object (id=-3)")
    if app_el.get("customClass") != "NSObject":
        raise I.XibError(f"{path}: Application customClass {app_el.get('customClass')!r} "
                         f"not probed ({where})")
    return _custom_object(b, app_el, "NSApplication", where)


def _xib_accessibility(b, objects, id_map, where, oid_count):
    """<accessibility description=...> archives an NSNibAXAttributeConnector
    outside the main connection/oid arrays (probe SidebarView [214], oid N+1).
    Returns (access_conns, access_oids, access_vals)."""
    access_conns = b.new("NSMutableArray")
    access_conns.add("NSInlinedValue", *b.boolean(False))
    ax_objs = []
    for tvel in objects.iter():
        ax_el = tvel.find("accessibility[@description]")
        if ax_el is None or tvel.get("id") not in id_map:
            continue
        c = b.new("NSNibAXAttributeConnector")
        axt = b.new("NSMutableString")
        axt.add("NS.bytes", N.DATA, b"AXDescription")
        c.add("AXDestinationArchiveKey", *b.ref(id_map[tvel.get("id")]))
        c.add("AXAttributeTypeArchiveKey", *b.ref(axt))
        c.add("AXAttributeValueArchiveKey",
              *b.ref(_localizable(b, tvel.get("id"), ax_el.get("description"),
                                  where,
                                  suffix=".ibExternalAccessibilityDescription")))
        ax_objs.append(c)
        access_conns.add("UINibEncoderEmptyKey", *b.ref(c))
    access_oids = b.new("NSArray")
    access_oids.add("NSInlinedValue", *b.boolean(False))
    if ax_objs:
        access_vals = b.new("NSArray")
        access_vals.add("NSInlinedValue", *b.boolean(False))
        for c in ax_objs:
            access_oids.add("UINibEncoderEmptyKey", *b.ref(c))
            access_vals.add("UINibEncoderEmptyKey",
                            *b.ref(b.number(*int_fit(oid_count + 1 + ax_objs.index(c)))))
    else:
        access_vals = access_oids
    return access_conns, access_oids, access_vals


def compile_xib(path):
    """Compile one macOS xib to NIBArchive bytes. Raises XibError."""
    doc, objects, where = _xib_parse(path)
    b = MacBuilder()
    # Oracle (reg-nnw-1818): xibs inside an .lproj directory are built by the
    # localized-variant step (project deployment target 15.0), which wraps user
    # strings in NSLocalizableString and clears NSAllowsLogicalLayoutDirection;
    # xibs outside any .lproj keep plain strings and the default-target flags.
    b.localize = ".lproj" in path
    res = doc.find("resources")
    if res is not None:
        _xib_resources(b, res)

    root = b.new("NSObject")
    ibd = b.new("NSIBObjectData")
    root.add("IB.objectdata", *b.ref(ibd))
    root.add("IB.systemFontUpdateVersion", *b.int8(1))

    id_map = {}      # xib id -> Obj (objects as they get built)
    conn_objs = []   # NSNibOutletConnector objects, document order
    late_pending = []  # (_Late, superview xib id) filled after connections
    late_menus = []    # (_Late, parent menu xib id) filled after the tree walk

    owner = _xib_owner(b, objects, path, where)
    id_map["-2"] = owner

    vis = b.new("NSMutableSet")
    vis.add("NSInlinedValue", *b.boolean(False))
    keys, vis_ids = _xib_visible_windows(b, objects, where, id_map, owner, vis)

    conns_arr = b.new("NSMutableArray")
    conns_arr.add("NSInlinedValue", *b.boolean(False))
    _xib_stackview_connector(b, objects, where, id_map, conns_arr, conn_objs,
                             late_pending)

    outlets, actions, bindings = [], [], []
    for src_el, conn_el in _conn_blocks(objects):
        if conn_el.tag == "binding":
            bindings.append((src_el, conn_el))
        elif conn_el.tag == "action":
            actions.append((src_el, conn_el))
        else:
            outlets.append((src_el, conn_el))

    # Outlets and actions both sort by SOURCE element id (ASCII), ties keep
    # document order (probe TimelineTableView: -2 < MjV < opA outlets); the
    # processing order drives lazy destination allocation.
    outlets.sort(key=lambda p: (p[0].get("id") or "").encode())
    for src_el, conn_el in outlets + sorted(
            actions, key=lambda p: (p[0].get("id") or "").encode()):
        if conn_el.tag == "action":
            _xib_action_connector(b, objects, where, id_map, conn_objs,
                                  conns_arr, late_menus, src_el, conn_el)
            continue
        _xib_outlet_connector(b, objects, owner, where, id_map, conn_objs,
                              conns_arr, late_pending, late_menus,
                              src_el, conn_el)
    # Bindings sort by SOURCE element id DESCENDING (probe GeneralPreferences:
    # wtY, Yrc, Ubm, UI6, Jwn, 6pw); outlets/actions keep ascending order.
    bind_key_pairs = []
    for src_el, conn_el in sorted(
            bindings, key=lambda p: (p[0].get("id") or "").encode(), reverse=True):
        c, key_pair = _xib_binding_connector(b, objects, owner, where,
                                             id_map, src_el, conn_el)
        if key_pair:
            bind_key_pairs.append(key_pair)
        conns_arr.add("UINibEncoderEmptyKey", *b.ref(c))
        conn_objs.append(c)
    for late, parent_id in late_pending:
        late.obj = id_map[parent_id]

    # Top-level objects never referenced by a connection and not menus (menus
    # are built by the tree walk below).
    for el in objects:
        if el.get("id") in ("-1", "-2", "-3") or el.tag == "placeholder":
            continue
        if el.get("id") not in id_map and el.tag != "menu":
            raise I.XibError(f"top-level <{el.tag} id='{el.get('id')}'> is never "
                             f"referenced; Apple's build order unknown ({where})")

    # NSObjectsKeys: NSApplication proxy, then the collected (obj, parent)
    # pairs. Allocation order (probe MainMenu): keys array shell first, then
    # the NSApplication proxy, then the tree-phase builds.
    keys_arr = b.new("NSArray")
    keys_arr.add("NSInlinedValue", *b.boolean(False))
    nsapp = _xib_app_proxy(b, objects, path, where)
    for el in objects:
        if el.get("id") in ("-1", "-2", "-3") or el.tag == "placeholder":
            continue
        if el.get("id") in vis_ids:
            continue
        if el.tag == "menu":
            _collect_menu_keys(b, el, owner, id_map, keys, where)
        elif el.tag == "userDefaultsController":
            # keyed once via bind_key_pairs below (golden GP [120] / Crash [22]
            # / Adv [58]+[59]: declared top-level UDCs never key from the doc
            # walk, only from their bindings)
            pass
        else:
            _collect_keys(b, el, owner, id_map, keys, where)
    keys.extend(bind_key_pairs)  # userDefaultsControllers (probe CrashReporter [131])
    for late, menu_id in late_menus:
        late.obj = id_map[menu_id]
    if any(isinstance(k, _DeferredPairs) for k in keys):
        expanded = []
        for k in keys:
            expanded.extend(k.fn()) if isinstance(k, _DeferredPairs) \
                else expanded.append(k)
        keys = expanded
    values = [(nsapp, owner)]
    values.extend(keys)
    keys_arr.add("UINibEncoderEmptyKey", *b.ref(nsapp))
    for obj, _parent in keys:
        keys_arr.add("UINibEncoderEmptyKey", *b.ref(obj))

    values_arr = b.new("NSArray")
    values_arr.add("NSInlinedValue", *b.boolean(False))
    for obj, parent in values:
        values_arr.add("UINibEncoderEmptyKey", *b.ref(parent))

    oids = [owner, nsapp] + [obj for obj, _ in keys] + conn_objs
    oids_keys_arr = b.new("NSArray")
    oids_keys_arr.add("NSInlinedValue", *b.boolean(False))
    for obj in oids:
        oids_keys_arr.add("UINibEncoderEmptyKey", *b.ref(obj))
    oids_values_arr = b.new("NSArray")
    oids_values_arr.add("NSInlinedValue", *b.boolean(False))
    numbers = []
    for i in range(1, len(oids) + 1):
        numbers.append(b.number(*int_fit(i)))
        oids_values_arr.add("UINibEncoderEmptyKey", *b.ref(numbers[-1]))
    access_conns, access_oids, access_vals = _xib_accessibility(
        b, objects, id_map, where, len(oids))

    ibd.add("NSRoot", *b.ref(owner))
    ibd.add("NSVisibleWindows", *b.ref(vis))
    ibd.add("NSConnections", *b.ref(conns_arr))
    ibd.add("NSObjectsKeys", *b.ref(keys_arr))
    ibd.add("NSObjectsValues", *b.ref(values_arr))
    ibd.add("NSOidsKeys", *b.ref(oids_keys_arr))
    ibd.add("NSOidsValues", *b.ref(oids_values_arr))
    ibd.add("NSAccessibilityConnectors", *b.ref(access_conns))
    ibd.add("NSAccessibilityOidsKeys", *b.ref(access_oids))
    ibd.add("NSAccessibilityOidsValues", *b.ref(access_vals))
    for late in b.late:
        if late.obj is None:
            raise I.XibError(f"{path}: a forward reference was never filled")
    return _finalize(b, root)

def _finalize(b, root):
    """Key table (__NSSetM order over first-intern order), class table, encode."""
    values, classes, class_idx = [], [], {}
    creation_keys, creation_idx = [], {}
    for o in b.objects:
        o.value_start = len(values)
        for key, v in o.values:
            if key not in creation_idx:
                creation_idx[key] = len(creation_keys)
                creation_keys.append(key)
            v.key_idx = creation_idx[key]
            values.append(v)
        o.value_count = len(values) - o.value_start
        if o.cls not in class_idx:
            class_idx[o.cls] = len(classes)
            classes.append([o.cls, ()])
    arch = N.Archive()
    arch.version = 1
    arch.minor = 10
    arch.keys = [k.encode("ascii") for k in creation_keys]
    arch.classes = [(name.encode("ascii") + b"\x00", extras) for name, extras in classes]
    arch.objects = [N.Object(class_idx[o.cls], o.value_start, o.value_count)
                    for o in b.objects]
    arch.values = values
    key_idx = {k: i for i, k in enumerate(creation_keys)}
    for o in b.objects:
        for key, v in o.values:
            v.key_idx = key_idx[key]
    for v in values:
        if isinstance(v.payload, _Late):
            v.payload = v.payload.obj.idx
    key_bytes = keyorder.key_order(keyorder.first_use_order(arch))
    remap = {k: i for i, k in enumerate(key_bytes)}
    assert len(remap) == len(creation_keys) and all(k in remap for k in creation_keys)
    for v in values:
        v.key_idx = remap[creation_keys[v.key_idx]]
    arch.keys = [k.encode("ascii") for k in key_bytes]
    return N.encode(arch, b"")  # macOS nibs have no LNE trailer


BUTTON_TYPE = {"push": 7, "check": 3, "switch": 3, "radio": 4, "bevel": 7,
               "roundRect": 7, "smallSquare": 7, "help": 7, "momentaryChange": 5}
BEZEL_STYLE = {"rounded": 1, "regularSquare": 2, "helpButton": 9, "recessed": 6,
               "roundedRect": 12, "smallSquare": 10, "texturedRounded": 12}
# (behavior attribute set, type, bezel, imagePosition, has image) ->
# NSButtonFlags / NSButtonFlags2 (oracle: TimelineContainerView bevel,
# AccountsReaderAPI roundRect, Dinosaurs help; push/check from golden-mac).
BUTTON_BEHAVIOR = {
    (("pushIn", "lightByBackground", "lightByGray"), "push", "rounded",
     None, False): (-2038415360, 129),
    (("pushIn", "lightByBackground", "lightByGray"), "help", "helpButton",
     None, False): (-2038415360, 161),
    (("pushIn", "lightByBackground", "lightByGray"), "bevel", "rounded",
     "overlaps", True): (-2042085376, 129),
    (("pushIn", "lightByBackground", "lightByGray"), "smallSquare",
     "smallSquare", "only", True): (-2034221056, 34),
    (("pushIn", "lightByBackground", "lightByGray"), "smallSquare",
     "smallSquare", "overlaps", True): (-2033696768, 162),
    (("pushIn", "lightByBackground", "lightByGray"), "roundRect", "roundedRect",
     None, False): (-2046803968, 164),
    (("changeContents", "doesNotDimImage", "lightByContents"), "check",
     "regularSquare", "left", False): (1211650304, 2),
    (("changeContents", "doesNotDimImage", "lightByContents"), "radio",
     "regularSquare", "left", False): (1211650304, 2),
}
# <popUpButtonCell type>: NSCellFlags, NSButtonFlags, NSButtonFlags2,
# NSBezelStyle, NSAuxButtonType (probe ImportOPMLSheet push,
# TimelineContainerView recessed).
POPUP_CELL = {
    "push": (-2076180416, 109068288, 129, 1, 0),
    "recessed": (67108928, -1233108992, 173, 13, 1),
}


def _key_equivalent(b, cell_el, where):
    s = cell_el.find("string[@key='keyEquivalent']")
    if s is None or not (s.text or "").strip():
        return b.string("")
    raw = s.text.strip().encode("utf-8")
    if s.get("base64-UTF8") == "YES":
        import base64
        raw = base64.b64decode(s.text.strip() + "=" * (-len(s.text.strip()) % 4))
    o = b.new("NSString")
    o.add("NS.bytes", N.DATA, raw)
    return o


DRAG_TYPES = ("Apple PDF pasteboard type", "Apple PICT pasteboard type",
              "Apple PNG pasteboard type", "NSFilenamesPboardType",
              "NeXT TIFF v4.0 pasteboard type",
              "com.apple.NSFilePromiseItemMetaData",
              "com.apple.pasteboard.promised-file-content-type",
              "dyn.ah62d4rv4gu8yc6durvwwa3xmrvw1gkdusm1044pxqyuha2pxsvw0e55bsmwca7d3sbwu")

IMAGE_SCALE = {"proportionallyDown": 0, "proportionallyUpOrDown": 3}

# (borderType, autohides, predominant, hScrollElasticity, hasHScroller attr)
# -> NSsFlags (oracle probes)
SCROLL_SFLAGS = {
    ("none", False, None, None, True): 198672,
    ("line", False, None, None, True): 198673,
    ("none", True, None, None, True): 199184,
    ("none", True, None, "none", True): 215568,
    ("none", True, "NO", None, False): 133680,
    ("none", True, "NO", None, True): 133680,  # probe CurrentActivity [19]
}


def _image_ref(b, name, where):
    """NSCustomResource for an <image name=...>; system-catalog names carry the
    system IBNamespaceID (probe: NSActionTemplate/NSFolder/circle vs app icons;
    probe AccountsPreferencesView proto: NS-prefixed names carry it even when
    not declared in <resources>)."""
    el = b.image_decls.get(name)
    system = name.startswith("NS") or (el is not None and el.get("catalog") == "system")
    key = (name, system)
    if key in b.images:
        return b.images[key]
    o = b.new("NSCustomResource")
    o.add("NSClassName", *b.ref(b.string("NSImage")))
    o.add("NSResourceName", *b.ref(b.string(name)))
    if el is not None and el.get("catalog") == "system":
        # probe CurrentActivity circle [198]: catalog resources carry
        # NSCatalogName before the namespace id
        o.add("NSCatalogName", *b.ref(b.string("system")))
    o.add("IBNamespaceID", *b.ref(b.string("system")) if system else (N.NIL, None))
    size = "{%s, %s}" % (el.get("width", "0"), el.get("height", "0")) if el is not None else None
    INTRINSIC = {"NSActionTemplate": "{19, 19}",  # probe DinosaursWindow [340]
                 "NSRemoveTemplate": "{18, 4}",   # probe AccountsPreferencesView [18]
                 "NSAddTemplate": "{18, 16}"}     # probe AccountsPreferencesView [107]
    if name in INTRINSIC:
        # declared sizes archive as the template's intrinsic size
        size = INTRINSIC[name]
    elif el is not None and el.get("catalog") == "system":
        # probe CurrentActivity circle [198]: declared 15x15 archives as the
        # symbol's intrinsic 32x32
        size = "{32, 32}"
    if size is not None:
        val = b.new("NSValue")
        val.add("NS.special", *b.int8(2))
        val.add("NS.sizeval", *b.ref(b.string(size)))
        o.add("IBDesignSize", *b.ref(val))
    else:
        o.add("IBDesignSize", *(N.NIL, None))
    o.add("IBDesignImageConfiguration", *(N.NIL, None))
    b.images[key] = o
    return o


def _image_view(b, el, where, superview, id_map, parent=None):
    """<imageView> -> NSImageView + NSImageCell (oracle BuiltinSmartFeedInspector)."""
    o = b.new("NSImageView")
    o.add("NSNextResponder", *(b.ref(superview) if superview is not None else (N.NIL, None)))
    o.add("NSNibTouchBar", *(N.NIL, None))
    v, vt = _vflags(el, where)
    o.add("NSvFlags", vt, v)
    id_map[el.get("id")] = o
    arr = b.new("NSMutableArray")
    arr.add("NSInlinedValue", *b.boolean(False))
    o.add("NSSubviews", *b.ref(arr))
    dt = b.new("NSMutableSet")
    dt.add("NSInlinedValue", *b.boolean(False))
    for t in DRAG_TYPES:
        dt.add("UINibEncoderEmptyKey", *b.ref(b.string(t)))
    o.add("NSDragTypes", *b.ref(dt))
    o.add("NSFrame", *b.ref(b.string(_rect(el, "frame", where))))
    if superview is not None:
        o.add("NSSuperview", *b.ref(superview))
    o.add("NSViewWantsBestResolutionOpenGLSurface", *b.boolean(False))
    if _translates(el):
        o.add("NSDoNotTranslateAutoresizingMask", *b.boolean(False))
    cons_el = el.find("constraints")
    cons = []
    if cons_el is not None and cons_el.findall("constraint"):
        carr = b.new("NSArray")
        carr.add("NSInlinedValue", *b.boolean(False))
        els = I._constraint_order(el, cons_el.findall("constraint"), where, mac=True)
        for c in els:
            con = _constraint(b, c, o, el.get("id"), id_map, {}, {}, where)
            cons.append(con)
            carr.add("UINibEncoderEmptyKey", *b.ref(con))
        b.cons_order[el.get("id")] = [c.get("id") for c in els]
        o.add("NSViewConstraints", *b.ref(carr))
    h, v2 = el.get("horizontalHuggingPriority"), el.get("verticalHuggingPriority")
    if (h is not None and h != "250") or (v2 is not None and v2 != "750"):
        o.add("NSHuggingPriority",
              *b.ref(b.string("{%s, %s}" % (_fmt_g(h or 250), _fmt_g(v2 or 750)))))
    o.add("IBNSSafeAreaLayoutGuide", *(N.NIL, None))
    o.add("IBNSLayoutMarginsGuide", *(N.NIL, None))
    o.add("IBNSClipsToBounds", *b.int8(0))
    o.add("NSEnabled", *b.boolean(False))
    cell_el = el.find("imageCell[@key='cell']")
    if cell_el is None:
        raise I.XibError(f"<imageView> without imageCell ({where})")
    cell = b.new("NSImageCell")
    cell.add("NSCellFlags", *int_fit(0))
    cell.add("NSCellFlags2", N.INT32, 33554432)
    img = cell_el.get("image")
    if img is not None:
        # probe AccountsReaderAPI [146]: imageless cells drop NSContents
        cell.add("NSContents", *b.ref(_image_ref(b, img, where)))
    cell.add("NSControlView", *b.ref(o))
    scale = cell_el.get("imageScaling", "proportionallyDown")
    if scale not in IMAGE_SCALE:
        raise I.XibError(f"imageScaling {scale!r} not probed ({where})")
    cell.add("NSAlign", *b.int8(0))
    cell.add("NSScale", *b.int8(IMAGE_SCALE[scale]))
    cell.add("NSStyle", *b.int8(0))
    cell.add("NSAnimates", *b.boolean(True))
    cell.add("NSImageAnimation", *int_fit(-1))
    o.add("NSCell", *b.ref(cell))
    id_map[el.get("id") + "#cell"] = cell
    id_map[cell_el.get("id")] = cell
    o.add("NSAllowsLogicalLayoutDirection", *b.boolean(not b.localize))
    o.add("NSControlSize", *b.int8(0))
    o.add("NSControlContinuous", *b.boolean(True))
    o.add("NSControlRefusesFirstResponder", *b.boolean(False))
    o.add("NSControlUsesSingleLineMode", *b.boolean(True))
    o.add("NSControlTextAlignment", *b.int8(0))
    o.add("NSControlLineBreakMode", *b.int8(0))
    o.add("NSControlWritingDirection", N.INT64, -1)
    o.add("NSControlSendActionMask", *b.int8(4))
    o.add("NSEditable", *b.boolean(cell_el.get("editable") == "YES"))
    o.add("NSImageViewPlaceholderPrecedence", *b.int8(0))
    o.add("IBNSShadowedSymbolConfiguration", *(N.NIL, None))
    return o, [(o, parent), (cell, o)] + [(c, o) for c in cons]


def _cursor(b, hotspot, kind):
    key = (hotspot, kind)
    if key in b.cursors:
        return b.cursors[key]
    o = b.new("NSCursor")
    o.add("NSHotSpot", *b.ref(b.string(hotspot)))
    o.add("NSCursorType", *int_fit(kind))
    b.cursors[key] = o
    return o


def _underline(b):
    return b.number(N.INT8, 1)


def _text_view(b, el, where, superview):
    """<textView> (+ custom class) -> swapper with the text stack (oracle About)."""
    o = b.new("NSClassSwapper" if el.get("customClass") else "NSTextView")
    if el.get("customClass"):
        o.add("NSClassName", *b.ref(b.string(I._swift_class(el))))
        o.add("NSOriginalClassName", *b.ref(b.string("NSTextView")))
    o.add("NSNextResponder", *(b.ref(superview) if superview is not None else (N.NIL, None)))
    o.add("NSNibTouchBar", *(N.NIL, None))
    v, vt = _vflags(el, where)
    o.add("NSvFlags", vt, v)
    r = el.find("rect[@key='frame']")
    vert = el.get("verticallyResizable") == "YES"
    if vert:
        o.add("NSFrameSize", *b.ref(b.string("{%s, %s}" % (_fmt_g(r.get("width")),
                                                           _fmt_g(r.get("height"))))))
    else:
        o.add("NSFrame", *b.ref(b.string(_rect(el, "frame", where))))
    max_sz = el.find("size[@key='maxSize']")
    max_s = "{%s, %s}" % (_fmt_g(max_sz.get("width")), _fmt_g(max_sz.get("height"))) \
        if max_sz is not None else "{0, 0}"

    tc = b.new("NSTextContainer")
    lm = b.new("NSLayoutManager")
    tc.add("NSLayoutManager", *b.ref(lm))
    tc.add("NSTextLayoutManager", *(N.NIL, None))
    tc.add("NSTextView", *b.ref(o))
    tc.add("NSWidth", N.DOUBLE, float(r.get("width")))
    tc.add("NSMinWidth", N.DOUBLE, 15.0)
    tc.add("NSTCFlags", *b.int8(1))
    ts = b.new("NSTextStorage")
    ms = b.new("NSMutableString")
    ms.add("NS.bytes", N.DATA, b"")
    ts.add("NSString", *b.ref(ms))
    ts.add("NSDelegate", *(N.NIL, None))
    lm.add("NSTextStorage", *b.ref(ts))
    tcs = b.new("NSMutableArray")
    tcs.add("NSInlinedValue", *b.boolean(False))
    tcs.add("UINibEncoderEmptyKey", *b.ref(tc))
    lm.add("NSTextContainers", *b.ref(tcs))
    lm.add("NSLMFlags", *b.int8(102))
    lm.add("NSDelegate", *(N.NIL, None))

    sd = b.new("NSTextViewSharedData")
    # NSFlags/NSMoreFlags/completion: probe series t0-t21 (macstudio
    # /tmp/mnprobe11, xibs in macnib-work/probe11) + corpus points
    # About direct/scroll, Crash, AL — fully orthogonal bits:
    #   0x1|0x800 base; 0x2 editable (default YES); 0x4 richText != NO;
    #   0x100 backgroundColor element present and drawsBackground != "NO";
    #   0x200 smartInsertDelete; 0x4000000 spellingCorrection;
    #   0x40000000 incrementalSearchingEnabled.
    # NSMoreFlags 0x2 follows the charPicker attr; the completion key is
    # TRUE unless a textCompletion attr archives false.
    rich = el.get("richText") != "NO"
    spell = el.get("spellingCorrection") == "YES"
    smart = el.get("smartInsertDelete") == "YES"
    bg_el = el.find("color[@key='backgroundColor']")
    flags = 0x1 | 0x800
    if rich:
        flags |= 0x4
    if el.get("editable") != "NO":
        flags |= 0x2
    if bg_el is not None and el.get("drawsBackground") != "NO":
        flags |= 0x100
    if smart:
        flags |= 0x200
    if spell:
        flags |= 0x4000000
    if el.get("incrementalSearchingEnabled") == "YES":
        flags |= 0x40000000
    sd.add("NSAutomaticTextCompletionDisabled",
           *b.boolean(el.get("textCompletion") is None))
    sd.add("NSFlags", *int_fit(flags))
    sd.add("NSMoreFlags", *b.int8(3 if el.get("allowsCharacterPickerTouchBarItem")
                                  is not None else 1))
    sd.add("NSTextCheckingTypes", *int_fit(0))
    sd.add("NSMarkedAttributes", *(N.NIL, None))
    bg = el.find("color[@key='backgroundColor']")
    sd.add("NSBackgroundColor", *b.ref(_color_ref(b, bg, where)))
    sel = b.new("NSDictionary")
    sel.add("NSInlinedValue", *b.boolean(False))
    sel.add("UINibEncoderEmptyKey", *b.ref(b.string("NSBackgroundColor")))
    sel.add("UINibEncoderEmptyKey",
            *b.ref(b.catalog_color("System", "selectedTextBackgroundColor", where)))
    sel.add("UINibEncoderEmptyKey", *b.ref(b.string("NSColor")))
    sel.add("UINibEncoderEmptyKey",
            *b.ref(b.catalog_color("System", "selectedTextColor", where)))
    sd.add("NSSelectedAttributes", *b.ref(sel))
    ins_el = el.find("color[@key='insertionPointColor']")
    sd.add("NSInsertionColor",
           *b.ref(_color_ref(b, ins_el, where) if ins_el is not None
                  else b.catalog_color("System", "textInsertionPointColor", where)))
    link = b.new("NSDictionary")
    link.add("NSInlinedValue", *b.boolean(False))
    link.add("UINibEncoderEmptyKey", *b.ref(b.string("NSColor")))
    link.add("UINibEncoderEmptyKey", *b.ref(b.catalog_color("System", "linkColor", where)))
    link.add("UINibEncoderEmptyKey", *b.ref(b.string("NSCursor")))
    link.add("UINibEncoderEmptyKey", *b.ref(_cursor(b, "{8, -8}", 13)))
    link.add("UINibEncoderEmptyKey", *b.ref(b.string("NSUnderline")))
    link.add("UINibEncoderEmptyKey", *b.ref(_underline(b)))
    sd.add("NSLinkAttributes", *b.ref(link))
    sd.add("NSDefaultParagraphStyle", *(N.NIL, None))
    sd.add("NSTextFinder", *(N.NIL, None))
    sd.add("NSPreferredTextFinderStyle", *b.int8(0))
    sd.add("NSTextHighlightAttributes", *(N.NIL, None))
    sd.add("NSWritingToolsFlags", *int_fit(256))

    o.add("NSSuperview", *(b.ref(superview) if superview is not None else (N.NIL, None)))
    if el.get("wantsLayer") == "YES":
        o.add("NSViewIsLayerTreeHost", *b.boolean(False))
    o.add("NSViewWantsBestResolutionOpenGLSurface", *b.boolean(False))
    o.add("IBNSSafeAreaLayoutGuide", *(N.NIL, None))
    o.add("IBNSLayoutMarginsGuide", *(N.NIL, None))
    o.add("IBNSClipsToBounds", *b.int8(0))
    o.add("NSTextContainer", *b.ref(tc))
    o.add("NSSharedData", *b.ref(sd))
    o.add("NSTVFlags", N.INT16, 134 if vert else 132)
    if vert:
        o.add("NSMaxSize", *b.ref(b.string(max_s)))
    o.add("NSDelegate", *(N.NIL, None))
    tc_el = el.find("color[@key='textColor']")
    if tc_el is not None:
        o.add("NSTextViewTextColor", *b.ref(_color_ref(b, tc_el, where)))
    return o


def _scroller(b, el, where, scroll):
    o = b.new("NSScroller")
    o.add("NSNextResponder", *b.ref(scroll))
    o.add("NSNibTouchBar", *(N.NIL, None))
    v, vt = _vflags(el, where)
    o.add("NSvFlags", vt, v)
    o.add("NSFrame", *b.ref(b.string(_rect(el, "frame", where))))
    o.add("NSSuperview", *b.ref(scroll))
    o.add("NSViewIsLayerTreeHost", *b.boolean(False))
    o.add("NSViewWantsBestResolutionOpenGLSurface", *b.boolean(False))
    o.add("IBNSSafeAreaLayoutGuide", *(N.NIL, None))
    o.add("IBNSLayoutMarginsGuide", *(N.NIL, None))
    o.add("IBNSClipsToBounds", *b.int8(0))
    o.add("NSAllowsLogicalLayoutDirection", *b.boolean(not b.localize))
    o.add("NSControlAction", *b.ref(b.string("_doScroller:")))
    o.add("NSControlTarget", *b.ref(scroll))
    o.add("NSControlSize", *b.int8(0))
    o.add("NSControlContinuous", *b.boolean(True))
    o.add("NSControlRefusesFirstResponder", *b.boolean(True))
    o.add("NSControlUsesSingleLineMode", *b.boolean(True))
    o.add("NSControlTextAlignment", *b.int8(0))
    o.add("NSControlLineBreakMode", *b.int8(0))
    o.add("NSControlWritingDirection", *int_fit(0))
    o.add("NSControlSendActionMask", *b.int8(4))
    if el.get("horizontal") == "YES":  # corpus: h-scroller only, hidden or not
        o.add("NSsFlags", *b.int8(1))
    o.add("NSTarget", *b.ref(scroll))
    o.add("NSAction", *b.ref(b.string("_doScroller:")))
    return o

def _ordered_constraints(b, el, o, where, id_map):
    """Element-ordered NSViewConstraints, all freshly built; returns them."""
    cons_el = el.find("constraints")
    cons = []
    if cons_el is not None and cons_el.findall("constraint"):
        carr = b.new("NSArray")
        carr.add("NSInlinedValue", *b.boolean(False))
        els = I._constraint_order(el, cons_el.findall("constraint"), where, mac=True)
        for c in els:
            con = _constraint(b, c, o, el.get("id"), id_map, {}, {}, where)
            carr.add("UINibEncoderEmptyKey", *b.ref(con))
            cons.append(con)
        b.cons_order[el.get("id")] = [c.get("id") for c in els]
        o.add("NSViewConstraints", *b.ref(carr))
    return cons


def _scroll_doc_view(b, el, cv_el, cv, where, id_map, carr):
    """Build (or reuse) the clip view's single document view: the owner's
    textView/tableView outlet may have built it lazily before the scroll view
    (probe CrashReporter / TimelineTableView: one stack, reused doc).
    Returns (doc, doc_el, is_table)."""
    subs = cv_el.find("subviews")
    doc_els = list(subs) if subs is not None else []
    if len(doc_els) != 1:
        raise I.XibError(f"<clipView> without exactly one subview ({where})")
    doc_el = doc_els[0]
    is_table = doc_el.tag in ("tableView", "outlineView")
    if is_table:
        # xibs may hang the headerView off the scrollView (probe
        # CurrentActivity); the table build owns it either way
        hv_out = el.find("tableHeaderView[@key='headerView']")
        if hv_out is not None and doc_el.find("tableHeaderView[@key='headerView']") is None:
            doc_el.append(hv_out)
    if doc_el.tag == "textView":
        doc = id_map.get(doc_el.get("id"))
        if doc is None:
            doc = _text_view(b, doc_el, where, cv)
            id_map[doc_el.get("id")] = doc
    elif is_table:
        doc = id_map.get(doc_el.get("id"))
        if doc is None:
            doc, _doc_pairs = _table_view(b, doc_el, where, cv, id_map, parent=cv)
    else:
        raise I.XibError(f"clipView subview <{doc_el.tag}> not probed ({where})")
    carr.add("UINibEncoderEmptyKey", *b.ref(doc))
    return doc, doc_el, is_table


def _scroll_header_clip(b, o, arr, hv_el):
    """The header clip view wrapping a table's headerView; joins the scroll
    view's subviews (probe CurrentActivity [19])."""
    hr = hv_el.find("rect[@key='frame']")
    hclip = b.new("NSClipView")
    hclip.add("NSNextResponder", *b.ref(o))
    hclip.add("NSNibTouchBar", *(N.NIL, None))
    hclip.add("NSvFlags", N.INT16, 256)
    harr = b.new("NSMutableArray")
    harr.add("NSInlinedValue", *b.boolean(False))
    hclip.add("NSSubviews", *b.ref(harr))
    hclip.add("NSFrameSize", *b.ref(b.string(
        "{%s, %s}" % (_fmt_g(hr.get("width")), _fmt_g(hr.get("height"))))))
    hclip.add("NSSuperview", *b.ref(o))
    hclip.add("NSNextKeyView", *b.ref(id_map[hv_el.get("id")]))
    hclip.add("NSViewWantsBestResolutionOpenGLSurface", *b.boolean(False))
    hclip.add("IBNSSafeAreaLayoutGuide", *(N.NIL, None))
    hclip.add("IBNSLayoutMarginsGuide", *(N.NIL, None))
    hclip.add("IBNSClipsToBounds", *b.int8(0))
    hclip.add("NSDocView", *b.ref(id_map[hv_el.get("id")]))
    hclip.add("NSAutomaticallyAdjustsContentInsets", *b.boolean(False))
    harr.add("UINibEncoderEmptyKey", *b.ref(id_map[hv_el.get("id")]))
    arr.add("UINibEncoderEmptyKey", *b.ref(hclip))
    # patch the header view's forward references to this clip
    doc._hdr_late.obj = hclip
    return hclip


def _pan_gesture(b, o):
    gest = b.new("NSArray")
    gest.add("NSInlinedValue", *b.boolean(False))
    pan = b.new("NSPanGestureRecognizer")
    pan.add("NSGestureRecognizer.allowedTouchTypes", *b.int8(1))
    pan.add("NSGestureRecognizer.action", *b.ref(b.string("_panWithGestureRecognizer:")))
    pan.add("NSGestureRecognizer.target", *b.ref(o))
    pan.add("NSGestureRecognizer.delegate", *b.ref(o))
    pan.add("NSPanGestureRecognizer.buttonMask", *b.int8(0))
    pan.add("NSPanGestureRecognizer.numberOfTouchesRequired", *b.int8(1))
    gest.add("UINibEncoderEmptyKey", *b.ref(pan))
    o.add("NSGestureRecognizers", *b.ref(gest))


def _scroll_view(b, el, where, superview, id_map, parent=None):
    """<scrollView> -> NSScrollView + NSClipView + scrollers + pan gesture."""
    key = (el.get("borderType", "bezel"), el.get("autohidesScrollers") == "YES",
           el.get("usesPredominantAxisScrolling"),
           el.get("horizontalScrollElasticity"),
           el.find("scroller[@key='horizontalScroller']") is not None
           or el.get("hasHorizontalScroller") is not None)
    if key not in SCROLL_SFLAGS:
        raise I.XibError(f"scrollView attr set {key} not probed ({where})")
    o = b.new("NSScrollView")
    o.add("NSNextResponder", *(b.ref(superview) if superview is not None else (N.NIL, None)))
    o.add("NSNibTouchBar", *(N.NIL, None))
    v, vt = _vflags(el, where)
    o.add("NSvFlags", vt, v)
    id_map[el.get("id")] = o
    arr = b.new("NSMutableArray")
    arr.add("NSInlinedValue", *b.boolean(False))
    o.add("NSSubviews", *b.ref(arr))
    cv_el = el.find("clipView[@key='contentView']")
    if cv_el is None:
        raise I.XibError(f"<scrollView> without clipView ({where})")
    cv = b.new("NSClipView")
    cv.add("NSNextResponder", *b.ref(o))
    cv.add("NSNibTouchBar", *(N.NIL, None))
    cv.add("NSvFlags", N.INT16, 256)
    cv_id = cv_el.get("id")
    id_map[cv_id] = cv
    carr = b.new("NSMutableArray")
    carr.add("NSInlinedValue", *b.boolean(False))
    cv.add("NSSubviews", *b.ref(carr))
    doc, doc_el, is_table = _scroll_doc_view(b, el, cv_el, cv, where, id_map, carr)
    arr.add("UINibEncoderEmptyKey", *b.ref(cv))
    r = cv_el.find("rect[@key='frame']")
    # probe CrashReporter golden [88]: a clipView with a non-zero xib origin
    # (borderType=line 1px inset) archives NSFrame, zero-origin keeps
    # NSFrameSize
    zero = r.get("x") in ("0", "0.0") and r.get("y") in ("0", "0.0")
    if zero:
        cv.add("NSFrameSize", *b.ref(b.string("{%s, %s}" % (_fmt_g(r.get("width")),
                                                            _fmt_g(r.get("height"))))))
    else:
        cv.add("NSFrame", *b.ref(b.string("{{%s, %s}, {%s, %s}}" % (
            r.get("x"), r.get("y"), _fmt_g(r.get("width")), _fmt_g(r.get("height"))))))
    hv_el0 = doc_el.find("tableHeaderView[@key='headerView']") if is_table else None
    if hv_el0 is not None:
        cv.add("NSBounds", *b.ref(b.string(
            "{{0, -%s}, {%s, %s}}" % (_fmt_g(hv_el0.find("rect[@key='frame']").get("height")),
                                      _fmt_g(r.get("width")),
                                      _fmt_g(r.get("height"))))))
    cv.add("NSSuperview", *b.ref(o))
    cv.add("NSNextKeyView", *b.ref(doc))
    cv.add("NSViewWantsBestResolutionOpenGLSurface", *b.boolean(False))
    cv.add("IBNSSafeAreaLayoutGuide", *(N.NIL, None))
    cv.add("IBNSLayoutMarginsGuide", *(N.NIL, None))
    cv.add("IBNSClipsToBounds", *b.int8(0))
    cv.add("NSDocView", *b.ref(doc))
    hv_el = doc_el.find("tableHeaderView[@key='headerView']") if is_table else None
    hclip = _scroll_header_clip(b, o, arr, hv_el) if hv_el is not None else None
    cv_flags = (0 if cv_el.get("drawsBackground") == "NO" else 4) \
        + (2 if cv_el.get("copiesOnScroll") == "NO" else 0)
    bg_el = cv_el.find("color[@key='backgroundColor']")
    nil_bg = cv_el.find("nil[@key='backgroundColor']") is not None
    if not nil_bg:
        if bg_el is not None:
            cv.add("NSBGColor", *b.ref(_color_ref(b, bg_el, where)))
        else:
            # golden ActivityLog/ErrorLog [21]: non-table clipViews without
            # an explicit backgroundColor archive controlBackgroundColor too
            cv.add("NSBGColor",
                   *b.ref(b.catalog_color("System", "controlBackgroundColor", where)))
    if not is_table:
        cv.add("NSCursor", *b.ref(_cursor(b, "{1, -1}", 0)))
    if cv_flags:
        cv.add("NScvFlags", *b.int8(cv_flags))
    cv.add("NSAutomaticallyAdjustsContentInsets", *b.boolean(False))
    h_el = el.find("scroller[@key='horizontalScroller']")
    v_el = el.find("scroller[@key='verticalScroller']")
    hs = _scroller(b, h_el, where, o) if h_el is not None else None
    vs = _scroller(b, v_el, where, o) if v_el is not None else None
    if hs is not None:
        arr.add("UINibEncoderEmptyKey", *b.ref(hs))
    if vs is not None:
        arr.add("UINibEncoderEmptyKey", *b.ref(vs))
    r2 = el.find("rect[@key='frame']")
    if float(r2.get("x", 0)) == 0 and float(r2.get("y", 0)) == 0:
        o.add("NSFrameSize", *b.ref(b.string(
            "{%s, %s}" % (_fmt_g(r2.get("width")), _fmt_g(r2.get("height"))))))
    else:
        o.add("NSFrame", *b.ref(b.string(_rect(el, "frame", where))))
    if superview is not None:
        o.add("NSSuperview", *b.ref(superview))
    o.add("NSNextKeyView", *b.ref(cv))
    o.add("NSViewWantsBestResolutionOpenGLSurface", *b.boolean(False))
    if _translates(el):
        o.add("NSDoNotTranslateAutoresizingMask", *b.boolean(False))
    scons = _ordered_constraints(b, el, o, where, id_map)
    _pan_gesture(b, o)
    o.add("IBNSSafeAreaLayoutGuide", *(N.NIL, None))
    o.add("IBNSLayoutMarginsGuide", *(N.NIL, None))
    o.add("IBNSClipsToBounds", *b.int8(0))
    o.add("NSsFlags", N.INT32, SCROLL_SFLAGS[key])
    if vs is not None:
        o.add("NSVScroller", *b.ref(vs))
        id_map[v_el.get("id")] = vs
    if hs is not None:
        o.add("NSHScroller", *b.ref(hs))
        id_map[h_el.get("id")] = hs
    o.add("NSContentView", *b.ref(cv))
    if hclip is not None:
        o.add("NSHeaderClipView", *b.ref(hclip))
    hls = float(el.get("horizontalLineScroll", 10))
    vls = float(el.get("verticalLineScroll", 10))
    if is_table:
        # line scrolls archive the table's row STRIDE: archived row height
        # plus intercell spacing height (goldens: Sidebar 32+0, TTT 96+0,
        # APV 24+2=26; the xib lineScroll attrs are ignored)
        rowh = _table_row_height(doc_el, where)
        size = doc_el.find("size[@key='intercellSpacing']")
        stride = rowh + (float(size.get("height")) if size is not None else 0.0)
        hls = vls = stride
    hps = float(el.get("horizontalPageScroll", 10))
    vps = float(el.get("verticalPageScroll", 10))
    if (hls, vls, hps, vps) != (10.0, 10.0, 10.0, 10.0):
        import struct as _struct
        o.add("NSScrollAmts", N.DATA, _struct.pack(">4f", hps, vps, hls, vls))
    o.add("NSMinMagnification", N.DOUBLE, 0.25)
    o.add("NSMaxMagnification", N.DOUBLE, 4.0)
    o.add("NSMagnification", N.DOUBLE, 1.0)
    pairs = [(o, parent), (cv, o), (doc, cv)]
    if is_table:
        pairs.append(_DeferredPairs(
            lambda: _table_pairs(b, doc_el, id_map)))
    if hs is not None:
        pairs.append((hs, o))
    if vs is not None:
        pairs.append((vs, o))
    if hv_el0 is not None and hv_el0.get("id") in id_map:
        # golden DinosaursWindow [120]: headerView keys under the scroll,
        # after the scrollers
        pairs.append((id_map[hv_el0.get("id")], o))
    pairs.extend((con, o) for con in scons)
    return o, pairs


def _color_ref(b, c_el, where):
    if c_el is None:
        raise I.XibError(f"missing color ({where})")
    if c_el.get("colorSpace") == "custom":
        return b.custom_color(c_el, where)
    return b.catalog_color(c_el.get("catalog"), c_el.get("name"), where)


def _button(b, el, where, superview, id_map, parent=None):
    """<button> -> NSButton with its NSButtonCell."""
    o = b.new("NSButton")
    o.add("NSNextResponder", *(b.ref(superview) if superview is not None else (N.NIL, None)))
    o.add("NSNibTouchBar", *(N.NIL, None))
    v, vt = _vflags(el, where)
    o.add("NSvFlags", vt, v)
    id_map[el.get("id")] = o
    if el.find("subviews") is not None:
        raise I.XibError(f"<button> with subviews not probed ({where})")
    o.add("NSFrame", *b.ref(b.string(_rect(el, "frame", where))))
    if superview is not None:
        o.add("NSSuperview", *b.ref(superview))
    o.add("NSViewWantsBestResolutionOpenGLSurface", *b.boolean(False))
    if _translates(el):
        o.add("NSDoNotTranslateAutoresizingMask", *b.boolean(False))
    # probe AccountsAddLocal Create button [59]: own <constraints> archive as
    # NSViewConstraints after NSDoNotTranslate, allocated before the cell
    cons_el = el.find("constraints")
    cons = []
    if cons_el is not None and cons_el.findall("constraint"):
        carr = b.new("NSArray")
        carr.add("NSInlinedValue", *b.boolean(False))
        els = I._constraint_order(el, cons_el.findall("constraint"), where, mac=True)
        for c in els:
            con = _constraint(b, c, o, el.get("id"), id_map, {}, {}, where)
            carr.add("UINibEncoderEmptyKey", *b.ref(con))
            cons.append(con)
        b.cons_order[el.get("id")] = [c.get("id") for c in els]
        o.add("NSViewConstraints", *b.ref(carr))
    cell_el = el.find("buttonCell[@key='cell']")
    if cell_el is None:
        raise I.XibError(f"<button> without buttonCell ({where})")
    btype = cell_el.get("type", "momentaryPushIn")
    # NSHuggingPriority: help writes iff (attr-or-default) differs from
    # (750,750) (probe CurrentActivity/Dinosaurs help 750/750 -> no key;
    # AccountStats 1000/1000 -> key); check/radio/bevel/smallSquare/roundRect
    # write whenever ANY hugging attr is present (probe TCV bevel v-only 750
    # -> key {250, 750}); push family writes iff differs from (250,750)
    # (probe ExportOPML eZ4 750/750 -> key, PPB v-only -> none).
    # NSAntiCompressionPriority only when a resistance attr differs from 750.
    h, v2 = el.get("horizontalHuggingPriority"), el.get("verticalHuggingPriority")
    if btype == "help":
        need = (h is not None and h != "750") or (v2 is not None and v2 != "750")
    elif btype in ("check", "radio", "bevel", "smallSquare", "roundRect"):
        need = h is not None or v2 is not None
    else:
        need = (h is not None and h != "250") or (v2 is not None and v2 != "750")
    if need:
        o.add("NSHuggingPriority",
              *b.ref(b.string("{%s, %s}" % (_fmt_g(h or 250), _fmt_g(v2 or 750)))))
    h, v2 = (el.get("horizontalCompressionResistancePriority"),
             el.get("verticalCompressionResistancePriority"))
    if (h is not None and h != "750") or (v2 is not None and v2 != "750"):
        o.add("NSAntiCompressionPriority",
              *b.ref(b.string("{%s, %s}" % (_fmt_g(h or 750), _fmt_g(v2 or 750)))))
    o.add("IBNSSafeAreaLayoutGuide", *(N.NIL, None))
    o.add("IBNSLayoutMarginsGuide", *(N.NIL, None))
    o.add("IBNSClipsToBounds", *b.int8(0))
    o.add("NSEnabled", *b.boolean(False))
    cell_el = el.find("buttonCell[@key='cell']")
    if cell_el is None:
        raise I.XibError(f"<button> without buttonCell ({where})")
    cell = _button_cell(b, cell_el, o, where)
    o.add("NSCell", *b.ref(cell))
    id_map[el.get("id") + "#cell"] = cell
    id_map[cell_el.get("id")] = cell
    tint = el.find("color[@key='contentTintColor']")
    if tint is not None:
        # <color> is a child of <button> but archives on the CELL (probe TCV [42]);
        # catalog=System -> catalog color, bare name -> <namedColor> resource
        # (probe AccountsFeedbin AccentColor)
        if tint.get("catalog") == "System":
            cell.add("NSContentTintColor",
                     *b.ref(b.catalog_color("System", tint.get("name"), where)))
        elif tint.get("catalog") is None and tint.get("name") in b.named_color_els:
            cell.add("NSContentTintColor",
                     *b.ref(b.named_color(tint.get("name"), where)))
        else:
            raise I.XibError(f"contentTintColor {tint.get('catalog')!r} not probed ({where})")
    o.add("NSAllowsLogicalLayoutDirection", *b.boolean(not b.localize))
    o.add("NSControlSize", *b.int8(0))
    if cell_el.get("controlSize") == "large":
        # probe ActivityLog copy button [108]: view mirrors the cell keys
        o.add("NSControlSize2", *b.int8(3))
        o.add("NSControlSizeExtraLarge", *b.boolean(True))
    o.add("NSControlContinuous", *b.boolean(True))
    o.add("NSControlRefusesFirstResponder", *b.boolean(True))
    o.add("NSControlUsesSingleLineMode",
          *b.boolean(cell_el.get("usesSingleLineMode") != "YES"))
    align = cell_el.get("alignment",
                        "natural" if btype in ("check", "radio") else "center")
    if align not in CONTROL_ALIGN:
        raise I.XibError(f"alignment {align!r} not probed ({where})")
    o.add("NSControlTextAlignment", *b.int8(CONTROL_ALIGN[align]))
    lb = cell_el.get("lineBreakMode", "wordWrap")
    if lb not in LINE_BREAK:
        raise I.XibError(f"lineBreakMode {lb!r} not probed ({where})")
    o.add("NSControlLineBreakMode", *b.int8(LINE_BREAK[lb]))
    o.add("NSControlWritingDirection", N.INT64, -1)
    o.add("NSControlSendActionMask", *b.int8(4))
    o.add("IBNSShadowedSymbolConfiguration", *(N.NIL, None))
    return o, [(o, parent)] + [(con, o) for con in cons] + [(cell, o)]


def _stepper(b, el, where, superview, id_map, parent=None):
    """<stepper> -> NSStepper with its NSStepperCell (probe DinosaursWindow [89])."""
    o = b.new("NSStepper")
    o.add("NSNextResponder", *(b.ref(superview) if superview is not None else (N.NIL, None)))
    o.add("NSNibTouchBar", *(N.NIL, None))
    v, vt = _vflags(el, where)
    o.add("NSvFlags", vt, v)
    id_map[el.get("id")] = o
    o.add("NSFrame", *b.ref(b.string(_rect(el, "frame", where))))
    if superview is not None:
        o.add("NSSuperview", *b.ref(superview))
    o.add("NSViewWantsBestResolutionOpenGLSurface", *b.boolean(False))
    if _translates(el):
        o.add("NSDoNotTranslateAutoresizingMask", *b.boolean(False))
    cons_el = el.find("constraints")
    cons = []
    if cons_el is not None and cons_el.findall("constraint"):
        carr = b.new("NSArray")
        carr.add("NSInlinedValue", *b.boolean(False))
        els = I._constraint_order(el, cons_el.findall("constraint"), where, mac=True)
        for c in els:
            con = _constraint(b, c, o, el.get("id"), id_map, {}, {}, where)
            carr.add("UINibEncoderEmptyKey", *b.ref(con))
            cons.append(con)
        b.cons_order[el.get("id")] = [c.get("id") for c in els]
        o.add("NSViewConstraints", *b.ref(carr))
    cell_el = el.find("stepperCell[@key='cell']")
    if cell_el is None:
        raise I.XibError(f"<stepper> without stepperCell ({where})")
    o.add("IBNSSafeAreaLayoutGuide", *(N.NIL, None))
    o.add("IBNSLayoutMarginsGuide", *(N.NIL, None))
    o.add("IBNSClipsToBounds", *b.int8(0))
    o.add("NSEnabled", *b.boolean(False))
    cell = b.new("NSStepperCell")
    align = cell_el.get("alignment", "left")
    if align not in CONTROL_ALIGN:
        raise I.XibError(f"alignment {align!r} not probed ({where})")
    cell.add("NSCellFlags", *int_fit(786464))
    cell.add("NSCellFlags2", *int_fit(_i32(TEXT_ALIGN[align] << 26)))
    cell.add("NSControlView", *b.ref(o))
    id_map[el.get("id") + "#cell"] = cell
    id_map[cell_el.get("id")] = cell
    if cell_el.get("minValue") is not None:
        cell.add("NSMinValue", N.DOUBLE, float(cell_el.get("minValue")))
    if cell_el.get("maxValue") is not None:
        cell.add("NSMaxValue", N.DOUBLE, float(cell_el.get("maxValue")))
    cell.add("NSIncrement", N.DOUBLE, float(cell_el.get("increment", 1)))
    cell.add("NSAutorepeat", *b.boolean(cell_el.get("autorepeat") == "YES"))
    o.add("NSCell", *b.ref(cell))
    o.add("NSAllowsLogicalLayoutDirection", *b.boolean(not b.localize))
    o.add("NSControlSize", *b.int8(0))
    # golden archives the VIEW's continuous state (default NO), not the
    # cell attr — DinosaursWindow cell continuous="YES" but key is false
    o.add("NSControlContinuous", *b.boolean(False))
    o.add("NSControlRefusesFirstResponder", *b.boolean(True))
    o.add("NSControlUsesSingleLineMode", *b.boolean(True))
    o.add("NSControlTextAlignment", *b.int8(CONTROL_ALIGN[align]))
    o.add("NSControlLineBreakMode", *b.int8(0))
    o.add("NSControlWritingDirection", N.INT64, -1)
    o.add("NSControlSendActionMask", *int_fit(65538))
    # view-level stepper keys archive fresh-NSStepper defaults (golden:
    # 0.0/0.0/0.0 even with cell maxValue=100), wraps+autorepeat true
    o.add("NSStepperMinValue", N.DOUBLE, 0.0)
    o.add("NSStepperMaxValue", N.DOUBLE, 0.0)
    o.add("NSStepperIncrement", N.DOUBLE, 0.0)
    o.add("NSStepperWraps", *b.boolean(True))
    o.add("NSStepperAutorepeat", *b.boolean(True))
    return o, [(o, parent)] + [(con, o) for con in cons] + [(cell, o)]


def _button_cell(b, el, control, where):
    o = b.new("NSButtonCell")
    btype = el.get("type", "momentaryPushIn")
    if btype in ("check", "radio"):
        # probe FeedInspector [52] / GP [175],[183]: check+radio cells archive
        # NSCellFlags 0x84000000 when state="on" else 0x4000000, and default
        # to natural alignment
        flags = 0x84000000 if el.get("state") == "on" else 0x4000000
        if el.get("state") not in (None, "on"):
            raise I.XibError(f"button state {el.get('state')!r} not probed ({where})")
        flags2 = TEXT_ALIGN[el.get("alignment", "natural")] << 26
    else:
        flags = 0x84000000 if el.get("state") == "on" else 0x4000000
        if btype == "smallSquare" and el.get("image"):
            # probe AccountsPreferencesView [14] remove/-106 add: pinned
            # words (enabled=NO is confounded with imagePosition; corpus
            # has remove=enabled-NO -> -1543503808, add -> -2080374720)
            flags = (-1543503808 if el.get("imagePosition") == "overlaps"
                     else -2080374720)
            flags2 = 134219776  # center<<26 | 0x180
        else:
            flags2 = TEXT_ALIGN[el.get("alignment", "center")] << 26
    o.add("NSCellFlags", *int_fit(_i32(flags)))
    o.add("NSCellFlags2", *int_fit(_i32(flags2)))
    if el.get("controlSize") == "large":
        # probe ActivityLog copy button [109]: after NSCellFlags2
        o.add("NSControlSize2", *b.int8(3))
        o.add("NSControlSizeExtraLarge", *b.boolean(True))
    o.add("NSContents", *b.ref(_localizable(b, el.get("id") or "",
                                            el.get("title", ""), where)))
    fd = el.find("font[@key='font']")
    # probe AccountsPreferencesView [16]: font-less buttonCells archive the
    # plain system font .AppleSystemUIFont 13/1044; the appearance font drops
    # NSFontUsesAppearanceFontSize (probe AccountsFeedbin [31])
    o.add("NSSupport", *b.ref(b.font(fd, where, appearance_key=False)
                              if fd is not None
                              else _plain_system_font(b, 13, 1044)))
    o.add("NSControlView", *b.ref(control))
    if btype not in BUTTON_TYPE:
        raise I.XibError(f"button type {btype!r} not probed ({where})")
    behavior = el.find("behavior[@key='behavior']")
    beh = behavior.attrib if behavior is not None else {}
    beh_key = tuple(k for k in beh if beh[k] == "YES" and k not in ("key",))
    bezel = el.get("bezelStyle", "rounded")
    if bezel not in BEZEL_STYLE:
        raise I.XibError(f"bezelStyle {bezel!r} not probed ({where})")
    image = el.get("image")
    key = (beh_key, btype, bezel, el.get("imagePosition"), image is not None)
    if key not in BUTTON_BEHAVIOR:
        raise I.XibError(f"button {sorted(beh_key)}/{btype}/{bezel} "
                         f"img={el.get('imagePosition')} not probed ({where})")
    bflags, bflags2 = BUTTON_BEHAVIOR[key]
    o.add("NSButtonFlags", *int_fit(_i32(bflags)))
    o.add("NSButtonFlags2", *int_fit(bflags2))
    o.add("NSBezelStyle", *b.int8(BEZEL_STYLE[bezel]))
    if image:
        o.add("NSNormalImage", *b.ref(_image_ref(b, image, where)))
    if btype in ("check", "radio"):
        # probe FeedInspector [56] / GP [126]: check -> NSSwitch, radio ->
        # NSRadioButton, between NSBezelStyle/NSNormalImage and
        # NSAlternateContents; one object shared by same-named cells
        name = "NSSwitch" if btype == "check" else "NSRadioButton"
        img = b.img_sources.get(name)
        if img is None:
            img = b.new("NSButtonImageSource")
            img.add("NSImageName", *b.ref(b.string(name)))
            b.img_sources[name] = img
        o.add("NSAlternateImage", *b.ref(img))
    o.add("NSAlternateContents", *b.ref(b.string("")))
    o.add("NSKeyEquivalent", *b.ref(_key_equivalent(b, el, where)))
    o.add("NSPeriodicDelay", N.INT16, 400)
    o.add("NSPeriodicInterval", *b.int8(75))
    o.add("NSAuxButtonType", *b.int8(BUTTON_TYPE[btype]))
    return o


MENU_CHECKMARK = {"on": ("NSMenuCheckmark", "{18, 16}"), None: ("NSMenuCheckmark", "{18, 16}")}
MENU_MIXED = ("NSMenuMixedState", "{18, 4}")

# systemMenu -> NSName (probe MainMenu golden)
MENU_SYSTEM_NAME = {"main": "_NSMainMenu", "apple": "_NSAppleMenu",
                    "services": "_NSServicesMenu", "window": "_NSWindowsMenu",
                    "help": "_NSHelpMenu"}
# keyEquivalentModifierMask bits over the NSCommandKeyMask base 1048576
MENU_MOD_BITS = {"option": 524288, "shift": 131072, "control": 262144}

# NSTvFlags is a packed word ibtool derives from the tableView/outlineView
# attribute set plus the canvas geometry (probe batch /tmp/tvprobes: single-bit
# attribute flips cascade through derived fields). Pinned per corpus attribute
# combination; unknown combos raise (same policy as SCROLL_SFLAGS).
TABLE_TVFLAGS = {
    (("allowsExpansionToolTips", "YES"), ("autosaveColumns", "NO"), ("columnAutoresizingStyle", "lastColumnOnly"), ("columnReordering", "NO"), ("columnResizing", "NO"), ("rowHeight", "96"), ("typeSelect", "NO"), ("verticalHuggingPriority", "750"), ("viewBased", "YES")): 438304768,  # TimelineTableView (tableView)
    (("allowsExpansionToolTips", "YES"), ("alternatingRowBackgroundColors", "YES"), ("autosaveColumns", "NO"), ("columnAutoresizingStyle", "firstColumnOnly"), ("columnReordering", "NO"), ("rowHeight", "24"), ("rowSizeStyle", "medium"), ("tableStyle", "inset"), ("verticalHuggingPriority", "750"), ("viewBased", "YES")): 1522532352,  # DinosaursWindow (tableView)
    (("allowsExpansionToolTips", "YES"), ("autosaveColumns", "NO"), ("columnAutoresizingStyle", "lastColumnOnly"), ("columnReordering", "NO"), ("columnResizing", "NO"), ("columnSelection", "YES"), ("multipleSelection", "NO"), ("rowHeight", "24"), ("tableStyle", "fullWidth"), ("verticalHuggingPriority", "750"), ("viewBased", "YES")): 371195904,  # AccountsPreferencesView (tableView)
    (("allowsExpansionToolTips", "YES"), ("alternatingRowBackgroundColors", "YES"), ("autosaveColumns", "NO"), ("columnAutoresizingStyle", "lastColumnOnly"), ("columnReordering", "NO"), ("multipleSelection", "NO"), ("rowHeight", "24"), ("rowSizeStyle", "medium"), ("tableStyle", "inset"), ("typeSelect", "NO"), ("verticalHuggingPriority", "750"), ("viewBased", "YES")): 1388314624,  # CurrentActivityWindow (tableView)
    (("allowsExpansionToolTips", "YES"), ("alternatingRowBackgroundColors", "YES"), ("autosaveName", "AccountStatsTable"), ("columnAutoresizingStyle", "firstColumnOnly"), ("multipleSelection", "NO"), ("rowHeight", "24"), ("rowSizeStyle", "medium"), ("tableStyle", "inset"), ("verticalHuggingPriority", "750"), ("viewBased", "YES")): 3552575488,  # AccountStatsWindow (tableView)
    (("allowsExpansionToolTips", "YES"), ("autosaveColumns", "NO"), ("columnAutoresizingStyle", "firstColumnOnly"), ("columnReordering", "NO"), ("columnResizing", "NO"), ("floatsGroupRows", "NO"), ("indentationPerLevel", "13"), ("rowHeight", "40"), ("rowSizeStyle", "systemDefault"), ("selectionHighlightStyle", "sourceList"), ("typeSelect", "NO"), ("verticalHuggingPriority", "750"), ("viewBased", "YES")): 440401920,  # SidebarView (outlineView)
}


def _tv_attr_key(el):
    return tuple(sorted((k, v) for k, v in el.attrib.items()
                        if k not in ("id", "customClass", "customModule",
                                     "customModuleProvider", "headerView",
                                     "outlineTableColumn")))


# Last-column canvas solve (probe p00 reproduces the golden TimelineTableView:
# a 447pt column in a 450pt table archives NSWidth 415; at 240/500/700 the
# solve differs, so the pin is geometry-exact).
TABLE_COL_SOLVE = {("447", "40", "1000", 450.0): 415.0}

# NSCellFlags for column dataCells (probe p16-p19): base 0x4000000 +
# 0x20 (lineBreak truncatingTail) + selectable (0x200000|0x1|0x20) +
# editable (0x10000000|0x20); flags2 = alignment<<26 | 0x800.
TABLE_HEADER_CELL_FLAGS = (75497536, 268437504)  # probe: constant for the
# truncatingTail/border header cells in the corpus


def _tv_int(v):
    return (N.INT64, v) if v < 0 else (N.INT8, v)


def _custom_image_resource(b, name, size, where):
    key = (name, size)
    if key in b.images:
        return b.images[key]
    o = b.new("NSCustomResource")
    o.add("NSClassName", *b.ref(b.string("NSImage")))
    o.add("NSResourceName", *b.ref(b.string(name)))
    o.add("IBNamespaceID", *(N.NIL, None))
    val = b.new("NSValue")
    val.add("NS.special", *b.int8(2))
    val.add("NS.sizeval", *b.ref(b.string(size)))
    o.add("IBDesignSize", *b.ref(val))
    o.add("IBDesignImageConfiguration", *(N.NIL, None))
    b.images[key] = o
    return o


def _xib_swapper(b, el, where):
    """Lazily-referenced customObject -> NSClassSwapper, NSObject original,
    NSInitializeWithInit=false (probe MainMenu [8] AppDelegate)."""
    o = b.new("NSClassSwapper")
    o.add("NSClassName", *b.ref(b.string(I._swift_class(el))))
    o.add("NSOriginalClassName", *b.ref(b.string("NSObject")))
    o.add("NSInitializeWithInit", *b.boolean(False))
    return o


def _menu_item(b, item_el, menu, cell, where, localize_owner=None):
    o = b.new("NSMenuItem")
    o.add("NSMenu", *b.ref(menu if menu is not None else _Late()))
    sep = item_el.get("isSeparatorItem") == "YES"
    if sep:
        # bug-compatible: false flags on separators (probe TCV [103])
        o.add("NSIsDisabled", *b.boolean(False))
        o.add("NSIsSeparator", *b.boolean(False))
    if item_el.get("hidden") == "YES":
        # inverted: hidden archives bool false (probe TCV [64])
        o.add("NSIsHidden", *b.boolean(False))
    o.add("NSAllowsKeyEquivalentLocalization", *b.boolean(False))
    o.add("NSAllowsKeyEquivalentMirroring", *b.boolean(False))
    if sep:
        o.add("NSTitle", *b.ref(b.string("")))
    else:
        o.add("NSTitle", *b.ref(_localizable(b, item_el.get("id") or "",
                                             item_el.get("title", ""), where)))
        if item_el.get("identifier"):
            o.add("NSMenuItemIdentifier", *b.ref(b.string(item_el.get("identifier"))))
    o.add("NSKeyEquiv", *b.ref(b.string("")))
    mod = item_el.find("modifierMask[@key='keyEquivalentModifierMask']")
    if mod is None and not sep:
        # the empty modifierMask element DROPS the key (probe TCV items vs
        # ImportOPML/AddFeed items without the element); separators never
        # carry it (probe TCV [103])
        o.add("NSKeyEquivModMask", N.INT32, 1048576)
    else:
        mask = 1048576
        extra = False
        for name, bit in (MENU_MOD_BITS.items() if mod is not None else ()):
            if mod.get(name) == "YES":
                mask += bit
                extra = True
        if extra:
            o.add("NSKeyEquivModMask", N.INT32, mask)
    o.add("NSMnemonicLoc", N.INT32, 2147483647)
    if item_el.get("state") == "on":
        o.add("NSState", *b.int8(1))
    on_name, on_size = MENU_CHECKMARK[item_el.get("state") if item_el.get("state") == "on" else None]
    o.add("NSOnImage", *b.ref(_custom_image_resource(b, on_name, on_size, where)))
    o.add("NSMixedImage", *b.ref(_custom_image_resource(b, MENU_MIXED[0], MENU_MIXED[1], where)))
    o.add("NSAction", *b.ref(b.string("_popUpItemAction:")))
    if item_el.get("tag") is not None:
        o.add("NSTag", *b.int_fit32(int(item_el.get("tag"))))
    o.add("NSTarget", *b.ref(cell))
    if item_el.find("attributedString[@key='attributedTitle']") is not None:
        at = b.new("NSAttributedString")
        at.add("NSString", *b.ref(b.string("")))
        o.add("NSAttributedTitle", *b.ref(at))
    o.add("NSHiddenInRepresentation", *b.boolean(True))
    return o


def _xib_menu_item(b, el, parent_menu, id_map, where):
    """Top-level <menuItem> with its full subtree; parent_menu is the parent
    NSMenu object or a _Late forward reference (probe MainMenu)."""
    o = b.new("NSMenuItem")
    o.add("NSMenu", *b.ref(parent_menu))
    if el.get("alternate") == "YES":
        # bug-compatible: xib alternate="YES" archives bool false (probe [189])
        o.add("NSIsAlternate", *b.boolean(False))
    sep = el.get("isSeparatorItem") == "YES"
    if sep:
        # bug-compatible: false flags on separators (probe [58])
        o.add("NSIsDisabled", *b.boolean(False))
        o.add("NSIsSeparator", *b.boolean(False))
    o.add("NSAllowsKeyEquivalentLocalization", *b.boolean(False))
    o.add("NSAllowsKeyEquivalentMirroring", *b.boolean(False))
    if sep:
        o.add("NSTitle", *b.ref(b.string("")))
    else:
        o.add("NSTitle", *b.ref(_localizable(b, el.get("id"), el.get("title", ""), where)))
        if el.get("identifier"):
            o.add("NSMenuItemIdentifier", *b.ref(b.string(el.get("identifier"))))
    ke = el.get("keyEquivalent") or ""
    o.add("NSKeyEquiv", *b.ref(b.string(ke)))
    if ke:
        mask = 1048576
        mod = el.find("modifierMask[@key='keyEquivalentModifierMask']")
        if mod is not None:
            for name, bit in MENU_MOD_BITS.items():
                if mod.get(name) == "YES":
                    mask += bit
            for name, val in mod.attrib.items():
                if val == "YES" and name not in MENU_MOD_BITS and name != "command":
                    raise I.XibError(f"modifierMask {name!r} not probed ({where})")
        o.add("NSKeyEquivModMask", N.INT32, mask)
    o.add("NSMnemonicLoc", N.INT32, 2147483647)
    o.add("NSOnImage", *b.ref(_custom_image_resource(b, "NSMenuCheckmark", "{18, 16}", where)))
    o.add("NSMixedImage", *b.ref(_custom_image_resource(b, "NSMenuMixedState", "{18, 4}", where)))
    if el.get("tag") is not None:
        o.add("NSTag", *b.int_fit32(int(el.get("tag"))))
    sub = el.find("menu[@key='submenu']")
    if sub is not None:
        # probe MainMenu [37]: NSAction string allocated before the submenu
        o.add("NSAction", *b.ref(b.string("submenuAction:")))
        sm = _xib_menu(b, sub, id_map, where)
        o.add("NSTarget", *b.ref(sm))
        o.add("NSSubmenu", *b.ref(sm))
    o.add("NSHiddenInRepresentation", *b.boolean(True))
    id_map[el.get("id")] = o
    return o


def _xib_menu(b, el, id_map, where):
    """Top-level/sub <menu>: title, items (reusing built ones), then NSName
    after the whole subtree (probe MainMenu [720]/[730]/[849])."""
    o = b.new("NSMenu")
    id_map[el.get("id")] = o
    title = el.get("title")
    if title:
        o.add("NSTitle", *b.ref(_localizable(b, el.get("id"), title, where)))
    else:
        o.add("NSTitle", *b.ref(b.string("")))
    iarr = b.new("NSMutableArray")
    iarr.add("NSInlinedValue", *b.boolean(False))
    o.add("NSMenuItems", *b.ref(iarr))
    items_el = el.find("items")
    for it in (items_el if items_el is not None else []):
        io = id_map.get(it.get("id"))
        if io is None:
            io = _xib_menu_item(b, it, o, id_map, where)
        iarr.add("UINibEncoderEmptyKey", *b.ref(io))
    name = MENU_SYSTEM_NAME.get(el.get("systemMenu"))
    if name:
        o.add("NSName", *b.ref(b.string(name)))
    return o


def _menu_parent_el(objects, ident):
    for m in objects.iter("menu"):
        items = m.find("items")
        if items is not None and any(it.get("id") == ident for it in items):
            return m
    return None


def _plain_system_font(b, size, flags):
    key = ("plain", size, flags)
    if key in b.fonts:
        return b.fonts[key]
    o = b.new("NSFont")
    o.add("NSName", *b.ref(b.string(".AppleSystemUIFont")))
    o.add("NSSize", *b.float64(float(size)))
    o.add("NSfFlags", *int_fit(flags))
    b.fonts[key] = o
    return o


def _header_font(b):
    """tableHeaderCell smallSystem: the text-style-descriptor variant
    (probe golden TimelineTableView [22]: 11pt, NSfFlags 16, Subhead)."""
    key = ("hdrsmall",)
    if key in b.fonts:
        return b.fonts[key]
    o = b.new("NSFont")
    o.add("NSName", *b.ref(b.string(".AppleSystemUIFont")))
    o.add("NSSize", *b.float64(11.0))
    o.add("NSfFlags", *int_fit(16))
    o.add("NSTextStyleDescriptor", *b.ref(b._style_descriptor("Subhead", 11.0)))
    o.add("NSHasWidth", *b.boolean(True))
    b.fonts[key] = o
    return o


def _table_header_cell(b, col_el, hc_el, where):
    o = b.new("NSTableHeaderCell")
    o.add("NSCellFlags", N.INT32, TABLE_HEADER_CELL_FLAGS[0])
    o.add("NSCellFlags2", N.INT32, TABLE_HEADER_CELL_FLAGS[1])
    title = hc_el.get("title")
    # golden TTT (font, no title) and SidebarView (neither) both archive
    # NSContents '' + the Subhead header font
    o.add("NSContents", *b.ref(_localizable(b, col_el.get("id") or "",
                                            title or "", where,
                                            suffix=".headerCell.title")))
    o.add("NSSupport", *b.ref(_header_font(b)))
    for key, store in (("backgroundColor", "NSBackgroundColor"),
                       ("textColor", "NSTextColor")):
        c = hc_el.find(f"color[@key='{key}']")
        if c is not None:
            o.add(store, *b.ref(_color_ref(b, c, where)))
    return o


def _table_data_cell(b, col_el, dc_el, table, where):
    o = b.new("NSTextFieldCell")
    flags = 0x4000000 + 0x40  # truncatingTail base (corpus lineBreakMode)
    if dc_el.get("lineBreakMode", "truncatingTail") != "truncatingTail":
        raise I.XibError(f"dataCell lineBreakMode not probed ({where})")
    if dc_el.get("selectable") == "YES":
        flags |= 0x200000 | 0x1
    if dc_el.get("editable") == "YES":
        flags |= 0x10000000
    o.add("NSCellFlags", N.INT32, flags)
    align = TEXT_ALIGN[dc_el.get("alignment", "natural")]
    o.add("NSCellFlags2", N.INT32, (align << 26) | 0x800)
    o.add("NSContents", *b.ref(_localizable(b, dc_el.get("id") or "",
                                            dc_el.get("title", ""), where)))
    fd = dc_el.find("font[@key='font']")
    o.add("NSSupport", *b.ref(b.font(fd, where) if fd is not None
                              else _plain_system_font(b, 13, 1044)))
    o.add("NSControlView", *b.ref(table))
    o.add("NSBackgroundColor",
          *b.ref(b.catalog_color("System", "controlBackgroundColor", where)))
    o.add("NSTextColor", *b.ref(b.catalog_color("System", "controlTextColor", where)))
    return o


def _table_column(b, col_el, table, table_el, id_map, where):
    o = b.new("NSTableColumn")
    ident = col_el.get("identifier")
    cols = table_el.find("tableColumns")
    if ident is None:
        ident = ("AutomaticTableColumnIdentifier.%d"
                 % list(cols).index(col_el) if cols is not None else 0)
    o.add("NSIdentifier", *b.ref(b.string(ident)))
    width = float(col_el.get("width", 100))
    solve = TABLE_COL_SOLVE.get((col_el.get("width"),
                                 col_el.get("minWidth"),
                                 col_el.get("maxWidth"),
                                 float(table_el.find("rect[@key='frame']").get("width"))))
    o.add("NSWidth", *b.float64(solve if solve is not None else width))
    o.add("NSMinWidth", *b.float64(float(col_el.get("minWidth", 10))))
    maxw = col_el.get("maxWidth")
    o.add("NSMaxWidth", *b.float64(3.4028234663852886e+38 if maxw is None
                                   else float(maxw)))
    hc_el = col_el.find("tableHeaderCell[@key='headerCell']")
    o.add("NSHeaderCell", *b.ref(_table_header_cell(b, col_el, hc_el, where)))
    dc_el = col_el.find("textFieldCell[@key='dataCell']")
    dc = _table_data_cell(b, col_el, dc_el, table, where)
    o.add("NSDataCell", *b.ref(dc))
    id_map[dc_el.get("id")] = dc
    mask = 0
    rm = col_el.find("tableColumnResizingMask[@key='resizingMask']")
    if rm is not None:
        if rm.get("resizeWithTable") == "YES":
            mask |= 1
        if rm.get("userResizable") == "YES":
            mask |= 2
    o.add("NSResizingMask", N.INT8, mask)
    o.add("NSIsResizeable", *b.boolean(False))
    if col_el.get("editable") != "NO":
        # bug-compat: default-editable columns archive false; editable="NO"
        # drops the key (probe golden [31] vs [18])
        o.add("NSIsEditable", *b.boolean(False))
    o.add("NSTableView", *b.ref(table))
    sd = col_el.find("sortDescriptor[@key='sortDescriptorPrototype']")
    if sd is not None:
        d = b.new("NSSortDescriptor")
        d.add("NSKey", *b.ref(b.string(sd.get("sortKey"))))
        d.add("NSAscending", *b.boolean(sd.get("ascending") == "YES"))
        d.add("NSSelector", *b.ref(b.string(sd.get("selector", "compare:"))))
        d.add("NSReverseNullOrder", *b.boolean(True))
        o.add("NSSortDescriptorPrototype", *b.ref(d))
    return o


def _corner_view(b, where):
    o = b.new("_NSCornerView")
    o.add("NSNextResponder", *(N.NIL, None))
    o.add("NSNibTouchBar", *(N.NIL, None))
    o.add("NSvFlags", N.INT16, 256)
    o.add("NSFrameSize", *b.ref(b.string("{17, 28}")))
    o.add("NSViewWantsBestResolutionOpenGLSurface", *b.boolean(False))
    o.add("IBNSSafeAreaLayoutGuide", *(N.NIL, None))
    o.add("IBNSLayoutMarginsGuide", *(N.NIL, None))
    o.add("IBNSClipsToBounds", *b.int8(0))
    return o


def _box(b, el, where, superview, id_map, parent=None):
    """<box boxType="separator"> (probe golden SidebarView [83]): NSBox with
    the default Title cell (smallSystem, textBackgroundColor/labelColor)."""
    if el.get("boxType", "primary") != "separator":
        raise I.XibError(f"boxType {el.get('boxType')!r} not probed ({where})")
    o = b.new("NSBox")
    o.add("NSNextResponder", *(b.ref(superview) if superview is not None else (N.NIL, None)))
    o.add("NSNibTouchBar", *(N.NIL, None))
    v, vt = _vflags(el, where)
    o.add("NSvFlags", vt, v)
    id_map[el.get("id")] = o
    arr = b.new("NSMutableArray")
    arr.add("NSInlinedValue", *b.boolean(False))
    o.add("NSSubviews", *b.ref(arr))
    r = el.find("rect[@key='frame']")
    if float(r.get("x", 0)) == 0 and float(r.get("y", 0)) == 0:
        o.add("NSFrameSize", *b.ref(b.string(
            "{%s, %s}" % (_fmt_g(r.get("width")), _fmt_g(r.get("height"))))))
    else:
        o.add("NSFrame", *b.ref(b.string(_rect(el, "frame", where))))
    if superview is not None:
        o.add("NSSuperview", *b.ref(superview))
    o.add("NSViewWantsBestResolutionOpenGLSurface", *b.boolean(False))
    if _translates(el):
        o.add("NSDoNotTranslateAutoresizingMask", *b.boolean(False))
    cons_el = el.find("constraints")
    if cons_el is not None and cons_el.findall("constraint"):
        carr = b.new("NSArray")
        carr.add("NSInlinedValue", *b.boolean(False))
        els = I._constraint_order(el, cons_el.findall("constraint"), where, mac=True)
        for c in els:
            con = _constraint(b, c, o, el.get("id"), id_map, {}, {}, where)
            carr.add("UINibEncoderEmptyKey", *b.ref(con))
        b.cons_order[el.get("id")] = [c.get("id") for c in els]
        o.add("NSViewConstraints", *b.ref(carr))
    h = el.get("horizontalHuggingPriority")
    v2 = el.get("verticalHuggingPriority")
    o.add("NSHuggingPriority", *b.ref(b.string(
        "{%s, %s}" % (_fmt_g(h or 250), _fmt_g(v2 or 750)))))
    o.add("IBNSSafeAreaLayoutGuide", *(N.NIL, None))
    o.add("IBNSLayoutMarginsGuide", *(N.NIL, None))
    o.add("IBNSClipsToBounds", *b.int8(0))
    o.add("NSOffsets", *b.ref(b.string("{5, 5}")))
    tc = b.new("NSTextFieldCell")
    tc.add("NSCellFlags", N.INT32, 67108864)
    tc.add("NSCellFlags2", N.INT32, 134217728)
    tc.add("NSContents", *b.ref(b.string(el.get("title") or "Title")))
    tc.add("NSSupport", *b.ref(_plain_system_font(b, 11, 3100)))
    tc.add("NSControlView", *(N.NIL, None))
    tc.add("NSBackgroundColor",
           *b.ref(b.catalog_color("System", "textBackgroundColor", where)))
    tc.add("NSTextColor", *b.ref(b.catalog_color("System", "labelColor", where)))
    o.add("NSTitleCell", *b.ref(tc))
    o.add("NSBorderType", *b.int8(3))
    o.add("NSBoxType", *b.int8(2))
    o.add("NSTitlePosition", *b.int8(2))
    o.add("NSTransparent", *b.boolean(True))
    return o, [(o, parent)]


def _progress_indicator(b, el, where, superview, id_map, parent=None):
    """<progressIndicator> (golden SidebarView bar+hidden 16389, AccountStats
    spinning small indeterminate 28935)."""
    style = el.get("style", "spinning")
    if style == "bar":
        if el.get("hidden") != "YES" or el.get("maxValue") != "100":
            raise I.XibError(f"bar progressIndicator attr set not probed ({where})")
        spi = 16389
    elif (style == "spinning" and el.get("indeterminate") == "YES"
          and el.get("displayedWhenStopped") == "NO"
          and el.get("controlSize") == "small" and el.get("maxValue") == "100"
          and el.get("hidden") is None):
        spi = 28935
    elif (style == "spinning" and el.get("indeterminate") == "YES"
          and el.get("displayedWhenStopped") == "NO"
          and el.get("controlSize") == "small" and el.get("bezeled") == "NO"
          and el.get("hidden") == "YES"):
        # probe AccountsFeedbin [76]: bezeled=NO clears one bit vs AccountStats
        spi = 28934
    else:
        raise I.XibError(f"progressIndicator style {style!r} attr set not probed ({where})")
    o = b.new("NSProgressIndicator")
    o.add("NSNextResponder", *(b.ref(superview) if superview is not None else (N.NIL, None)))
    o.add("NSNibTouchBar", *(N.NIL, None))
    v, vt = _vflags(el, where)
    o.add("NSvFlags", vt, v)
    id_map[el.get("id")] = o
    r = el.find("rect[@key='frame']")
    if float(r.get("x", 0)) == 0 and float(r.get("y", 0)) == 0:
        o.add("NSFrameSize", *b.ref(b.string(
            "{%s, %s}" % (_fmt_g(r.get("width")), _fmt_g(r.get("height"))))))
    else:
        o.add("NSFrame", *b.ref(b.string(_rect(el, "frame", where))))
    if superview is not None:
        o.add("NSSuperview", *b.ref(superview))
    if el.get("wantsLayer") == "YES":
        o.add("NSViewIsLayerTreeHost", *b.boolean(False))
    o.add("NSViewWantsBestResolutionOpenGLSurface", *b.boolean(False))
    if _translates(el):
        o.add("NSDoNotTranslateAutoresizingMask", *b.boolean(False))
    cons_el = el.find("constraints")
    if cons_el is not None and cons_el.findall("constraint"):
        carr = b.new("NSArray")
        carr.add("NSInlinedValue", *b.boolean(False))
        els = I._constraint_order(el, cons_el.findall("constraint"), where, mac=True)
        for c in els:
            con = _constraint(b, c, o, el.get("id"), id_map, {}, {}, where)
            carr.add("UINibEncoderEmptyKey", *b.ref(con))
        b.cons_order[el.get("id")] = [c.get("id") for c in els]
        o.add("NSViewConstraints", *b.ref(carr))
    h = el.get("horizontalHuggingPriority")
    v2 = el.get("verticalHuggingPriority")
    o.add("NSHuggingPriority", *b.ref(b.string(
        "{%s, %s}" % (_fmt_g(h or 250), _fmt_g(v2 or 250)))))
    o.add("IBNSSafeAreaLayoutGuide", *(N.NIL, None))
    o.add("IBNSLayoutMarginsGuide", *(N.NIL, None))
    o.add("IBNSClipsToBounds", *b.int8(0))
    o.add("NSpiFlags", *int_fit(spi))
    o.add("NSMaxValue", N.DOUBLE, float(el.get("maxValue", 100)))
    return o, [(o, parent)]


def _compile_cell_nib(cell_el, where, localize, ident=None):
    """Prototype <tableCellView> -> standalone NIBArchive bytes (golden
    SidebarView [57]/[60]: NSTableViewArchivedReusableViewsKey NSNib payloads;
    proxy owner NSObject, NSApplication proxy, cell's own outlets)."""
    b = MacBuilder()
    b.localize = localize
    b.proto_mode = True
    root = b.new("NSObject")
    ibd = b.new("NSIBObjectData")
    root.add("IB.objectdata", *b.ref(ibd))
    root.add("IB.systemFontUpdateVersion", *b.int8(1))
    id_map = {}
    owner = b.new("NSCustomObject")
    owner.add("NSClassName", *b.ref(b.string("NSObject")))
    vis = b.new("NSMutableSet")
    vis.add("NSInlinedValue", *b.boolean(False))
    conns_arr = b.new("NSMutableArray")
    conns_arr.add("NSInlinedValue", *b.boolean(False))
    conn_els = cell_el.findall("connections/outlet")
    # golden Dinosaurs feed proto [6]/[62]: the FIRST outlet connector
    # allocates before the tree, later ones right after it post-tree
    conn_first = b.new("NSNibOutletConnector") if conn_els else None
    if conn_first is not None:
        conns_arr.add("UINibEncoderEmptyKey", *b.ref(conn_first))
    if not conn_els:
        # golden DataCell proto57 [6]: with no outlets the keys shell lands
        # right after the connections array, before the cell tree
        keys_arr = b.new("NSArray")
    cell, pairs = _table_cell_view(b, cell_el, where, None, id_map,
                                   parent=owner, ident=ident)
    # golden Dinosaurs feed proto: embedded tree pairs order textField
    # groups before imageView groups (same tf<img precedence as constraint
    # groups), unlike the inline doc-order pairs
    groups, cur = [], []
    for pair in pairs[1:]:
        cur.append(pair)
        if pair[1] is cell:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    groups.sort(key=lambda g: 0 if g[0][0].cls in ("NSTextField",
                                                   "NSSecureTextField") else 1)
    flat = [p for g in groups for p in g]
    keys = [cell]
    if conn_els:
        c = conn_first
        c.add("NSSource", *b.ref(cell))
        c.add("NSDestination", *b.ref(id_map[conn_els[0].get("destination")]))
        c.add("NSLabel", *b.ref(b.string(conn_els[0].get("property"))))
        c.add("NSChildControllerCreationSelectorName", *(N.NIL, None))
    conns = [conn_first] if conn_first else []
    for conn_el in conn_els[1:]:
        c = b.new("NSNibOutletConnector")
        conns_arr.add("UINibEncoderEmptyKey", *b.ref(c))
        c.add("NSSource", *b.ref(cell))
        c.add("NSDestination", *b.ref(id_map[conn_el.get("destination")]))
        c.add("NSLabel", *b.ref(b.string(conn_el.get("property"))))
        c.add("NSChildControllerCreationSelectorName", *(N.NIL, None))
        conns.append(c)
    if conn_els:
        # golden HeaderCell proto60 [27]: keys shell after the label strings
        keys_arr = b.new("NSArray")
    nsapp = b.new("NSCustomObject")
    nsapp.add("NSClassName", *b.ref(b.string("NSApplication")))
    keys.extend(o2 for o2, _ in flat)
    keys.append(nsapp)
    values = [owner] + [p for _, p in flat] + [owner]
    keys_arr.add("NSInlinedValue", *b.boolean(False))
    values_arr = b.new("NSArray")
    values_arr.add("NSInlinedValue", *b.boolean(False))
    for o2, p2 in zip(keys, values):
        keys_arr.add("UINibEncoderEmptyKey", *b.ref(o2))
        values_arr.add("UINibEncoderEmptyKey", *b.ref(p2))
    oids = [owner] + keys + conns
    ok_arr = b.new("NSArray")
    ok_arr.add("NSInlinedValue", *b.boolean(False))
    ov_arr = b.new("NSArray")
    ov_arr.add("NSInlinedValue", *b.boolean(False))
    for i, o2 in enumerate(oids, 1):
        ok_arr.add("UINibEncoderEmptyKey", *b.ref(o2))
        ov_arr.add("UINibEncoderEmptyKey", *b.ref(b.number(*int_fit(i))))
    axc = b.new("NSMutableArray")
    axc.add("NSInlinedValue", *b.boolean(False))
    axk = b.new("NSArray")
    axk.add("NSInlinedValue", *b.boolean(False))
    ibd.add("NSRoot", *b.ref(owner))
    ibd.add("NSVisibleWindows", *b.ref(vis))
    ibd.add("NSConnections", *b.ref(conns_arr))
    ibd.add("NSObjectsKeys", *b.ref(keys_arr))
    ibd.add("NSObjectsValues", *b.ref(values_arr))
    ibd.add("NSOidsKeys", *b.ref(ok_arr))
    ibd.add("NSOidsValues", *b.ref(ov_arr))
    ibd.add("NSAccessibilityConnectors", *b.ref(axc))
    ibd.add("NSAccessibilityOidsKeys", *b.ref(axk))
    ibd.add("NSAccessibilityOidsValues", *b.ref(axk))
    return _finalize(b, root)


def _table_row_height(el, where):
    rss = el.get("rowSizeStyle")
    if rss is None:
        return float(el.get("rowHeight", 17))
    if rss == "medium":
        return 24.0
    if rss == "systemDefault":
        return 32.0 if el.get("selectionHighlightStyle") == "sourceList" else 24.0
    raise I.XibError(f"rowSizeStyle {rss!r} not probed ({where})")


def _table_pairs(b, doc_el, id_map):
    """Key pairs for a table/outline subtree (golden DinosaursWindow: per
    column (col, table), (dataCell, col), (proto cell, col), proto subtree,
    proto's own constraints; headerCell/cornerView never keyed). Called via
    _DeferredPairs after the connections walk: prototype cells build lazily."""
    pairs = []
    cols_el = doc_el.find("tableColumns")
    for col_el in (cols_el if cols_el is not None else []):
        col = id_map[col_el.get("id")]
        pairs.append((col, id_map[doc_el.get("id")]))
        dc_el = col_el.find("textFieldCell[@key='dataCell']")
        if dc_el is not None:
            pairs.append((id_map[dc_el.get("id")], col))
        for pv in col_el.findall("prototypeCellViews/tableCellView"):
            pobj = id_map[pv.get("id")]
            pairs.append((pobj, col))
            subs = pv.find("subviews")
            for child in (subs if subs is not None else []):
                cid = child.get("id")
                cobj = id_map[cid]
                pairs.append((cobj, pobj))
                if cid + "#cell" in id_map:
                    pairs.append((id_map[cid + "#cell"], cobj))
                fel = child.find("*[@key='cell']/numberFormatter[@key='formatter']")
                if fel is not None and fel.get("id") in id_map:
                    pairs.append((id_map[fel.get("id")],
                                  id_map[cid + "#cell"]))
                for c2 in b.cons_order.get(cid, []):
                    pairs.append((id_map[c2], cobj))
            for c3 in b.cons_order.get(pv.get("id"), []):
                pairs.append((id_map[c3], pobj))
    return pairs


def _table_view(b, el, where, superview, id_map, parent=None):
    """<tableView>/<outlineView> (+ customClass -> NSClassSwapper)."""
    is_outline = el.tag == "outlineView"
    o = b.new("NSClassSwapper" if el.get("customClass")
              else ("NSOutlineView" if is_outline else "NSTableView"))
    if el.get("customClass"):
        o.add("NSClassName", *b.ref(b.string(I._swift_class(el))))
        o.add("NSOriginalClassName",
              *b.ref(b.string("NSOutlineView" if is_outline else "NSTableView")))
    o.add("NSNextResponder", *(b.ref(superview) if superview is not None else (N.NIL, None)))
    o.add("NSNibTouchBar", *(N.NIL, None))
    v, vt = _vflags(el, where)
    if v == 256 and el.find("autoresizingMask[@key='autoresizingMask']") is not None:
        # the canvas solves the table to fill its clip (probe golden: empty
        # autoresizingMask archives widthSizable|heightSizable)
        v = 256 | I.RESIZE_FLAGS["widthSizable"] | I.RESIZE_FLAGS["heightSizable"]
    o.add("NSvFlags", vt, v)
    mask_el = el.find("autoresizingMask[@key='autoresizingMask']")
    if mask_el is not None and len(mask_el.attrib) > 1:
        # explicit autoresizing -> golden archives an EMPTY NSSubviews array
        # (golden SidebarView [14]; TTT's empty mask omits the key)
        arr0 = b.new("NSMutableArray")
        arr0.add("NSInlinedValue", *b.boolean(False))
        o.add("NSSubviews", *b.ref(arr0))
    id_map[el.get("id")] = o
    r = el.find("rect[@key='frame']")
    if float(r.get("x", 0)) == 0 and float(r.get("y", 0)) == 0:
        o.add("NSFrameSize", *b.ref(b.string(
            "{%s, %s}" % (_fmt_g(r.get("width")), _fmt_g(r.get("height"))))))
    else:
        o.add("NSFrame", *b.ref(b.string(_rect(el, "frame", where))))
    if superview is not None:
        o.add("NSSuperview", *b.ref(superview))
    o.add("NSViewWantsBestResolutionOpenGLSurface", *b.boolean(False))
    if _translates(el):
        o.add("NSDoNotTranslateAutoresizingMask", *b.boolean(False))
    o.add("IBNSSafeAreaLayoutGuide", *(N.NIL, None))
    o.add("IBNSLayoutMarginsGuide", *(N.NIL, None))
    o.add("IBNSClipsToBounds", *b.int8(0))
    o.add("NSEnabled", *b.boolean(False))
    o.add("NSAllowsLogicalLayoutDirection", *b.boolean(not b.localize))
    o.add("NSControlAllowsExpansionToolTips",
          *b.boolean(el.get("allowsExpansionToolTips") != "YES"))
    o.add("NSControlSize", *b.int8(0))
    o.add("NSControlContinuous", *b.boolean(True))
    o.add("NSControlRefusesFirstResponder", *b.boolean(True))
    o.add("NSControlUsesSingleLineMode", *b.boolean(True))
    o.add("NSControlTextAlignment", *b.int8(0))
    o.add("NSControlLineBreakMode", *b.int8(0))
    o.add("NSControlWritingDirection", *b.int8(0))
    o.add("NSControlSendActionMask", *b.int8(0))
    hv_el = el.find("tableHeaderView[@key='headerView']")
    if hv_el is not None:
        late_clip = _Late()
        hv = b.new("NSTableHeaderView")
        hv.add("NSNextResponder", *b.ref(late_clip))
        hv.add("NSNibTouchBar", *(N.NIL, None))
        hv.add("NSvFlags", N.INT16, 256)
        hr = hv_el.find("rect[@key='frame']")
        hv.add("NSFrameSize", *b.ref(b.string(
            "{%s, %s}" % (_fmt_g(hr.get("width")), _fmt_g(hr.get("height"))))))
        hv.add("NSSuperview", *b.ref(late_clip))
        hv.add("NSViewIsLayerTreeHost", *b.boolean(False))
        hv.add("NSViewWantsBestResolutionOpenGLSurface", *b.boolean(False))
        hv.add("IBNSSafeAreaLayoutGuide", *(N.NIL, None))
        hv.add("IBNSLayoutMarginsGuide", *(N.NIL, None))
        hv.add("IBNSClipsToBounds", *b.int8(0))
        hv.add("NSTableView", *b.ref(o))
        id_map[hv_el.get("id")] = hv
        o._hdr_late = late_clip
        o.add("NSHeaderView", *b.ref(hv))
    o.add("NSCornerView", *b.ref(_corner_view(b, where)))
    cols_arr = b.new("NSMutableArray")
    cols_arr.add("NSInlinedValue", *b.boolean(False))
    o.add("NSTableColumns", *b.ref(cols_arr))
    cols_el = el.find("tableColumns")
    for col_el in (cols_el if cols_el is not None else []):
        col = _table_column(b, col_el, o, el, id_map, where)
        cols_arr.add("UINibEncoderEmptyKey", *b.ref(col))
        id_map[col_el.get("id")] = col
    size = el.find("size[@key='intercellSpacing']")
    o.add("NSIntercellSpacingWidth",
          *b.float64(float(size.get("width")) if size is not None else 0.0))
    o.add("NSIntercellSpacingHeight",
          *b.float64(float(size.get("height")) if size is not None else 0.0))
    bg = el.find("color[@key='backgroundColor']")
    if bg is None:
        raise I.XibError(f"<{el.tag}> without backgroundColor ({where})")
    o.add("NSBackgroundColor", *b.ref(_color_ref(b, bg, where)))
    grid_el = el.find("color[@key='gridColor']")
    o.add("NSGridColor", *b.ref(b.catalog_color(
        "System", grid_el.get("name") if grid_el is not None else "gridColor",
        where)))
    rss = el.get("rowSizeStyle")
    rowh = _table_row_height(el, where)
    o.add("NSRowHeight", *b.float64(rowh))
    key = _tv_attr_key(el)
    if key not in TABLE_TVFLAGS:
        raise I.XibError(f"<{el.tag}> attr set "
                         f"{sorted(k for k, _ in key)} not probed ({where})")
    o.add("NSTvFlags", N.INT32, _i32(TABLE_TVFLAGS[key]))
    o.add("NSDelegate", *(N.NIL, None))
    o.add("NSDataSource", *(N.NIL, None))
    if el.get("autosaveName"):
        o.add("NSAutosaveName", *b.ref(b.string(el.get("autosaveName"))))
    cas = el.get("columnAutoresizingStyle", "uniform")
    cas_map = {"uniform": 1, "lastColumnOnly": 4, "firstColumnOnly": 5}
    if cas not in cas_map:
        raise I.XibError(f"columnAutoresizingStyle {cas!r} not probed ({where})")
    o.add("NSColumnAutoresizingStyle", *b.int8(cas_map[cas]))
    o.add("NSDraggingSourceMaskForLocal", N.INT64, -1)
    o.add("NSDraggingSourceMaskForNonLocal", *b.int8(0))
    o.add("NSAllowsTypeSelect", *b.boolean(el.get("typeSelect") == "NO"))
    if el.get("selectionHighlightStyle"):
        if el.get("selectionHighlightStyle") != "sourceList":
            raise I.XibError("selectionHighlightStyle not probed")
        o.add("NSTableViewSelectionHighlightStyle", *b.int8(1))
    if el.get("tableStyle"):
        if el.get("tableStyle") not in ("inset", "fullWidth"):
            raise I.XibError("tableStyle not probed")
        # probe AccountsPreferencesView [31]: fullWidth archives 1, inset 2
        o.add("NSTableViewStyle",
              *b.int8(2 if el.get("tableStyle") == "inset" else 1))
    o.add("NSTableViewDraggingDestinationStyle",
          *b.int8(1 if el.get("selectionHighlightStyle") == "sourceList" else 0))
    protos = []
    for col_el in (cols_el if cols_el is not None else []):
        pvs = col_el.find("prototypeCellViews")
        for pv in (pvs if pvs is not None else []):
            # the dict key is the cell identifier, else the column's (probe
            # CurrentActivity [84]: identifier-less cell keyed 'activity')
            ident = pv.get("identifier") or col_el.get("identifier")
            if ident is None:
                raise I.XibError(f"prototypeCellView without identifier ({where})")
            protos.append((ident, pv, col_el))
    if rss is not None or protos:
        # golden SidebarView [54]: identifier -> NSNib(embedded cell archive),
        # entries sorted by identifier
        reusables = b.new("NSMutableDictionary")
        reusables.add("NSInlinedValue", *b.boolean(False))
        for ident, pv, col in sorted(protos, key=lambda t: t[0].encode()):
            reusables.add("UINibEncoderEmptyKey", *b.ref(b.string(ident)))
            nib = b.new("NSNib")
            reusables.add("UINibEncoderEmptyKey", *b.ref(nib))
            data = b.new("NSData")
            nib.add("NSNibFileData", *b.ref(data))
            nib.add("NSNibFileIsKeyed", *b.boolean(False))
            nib.add("NSNibFileUseParentBundle", *b.boolean(False))
            nib.add("NSNibFileImages", *(N.NIL, None))
            nib.add("NSNibFileSounds", *(N.NIL, None))
            data.add("NS.bytes", N.DATA,
                     _compile_cell_nib(pv, where, b.localize,
                                       ident=col.get("identifier")))
        o.add("NSTableViewArchivedReusableViewsKey", *b.ref(reusables))
    if el.get("floatsGroupRows") is not None:
        # bug-compat: floatsGroupRows="NO" archives true
        o.add("NSTableViewShouldFloatGroupRows",
              *b.boolean(el.get("floatsGroupRows") != "YES"))
    o.add("NSTableViewGroupRowStyle", *b.int8(1))
    if rss is not None:
        o.add("NSTableViewRowSizeStyle", *_tv_int(
            -1 if rss == "systemDefault" else 2))
    if is_outline:
        o.add("NSOutlineViewAutoresizesOutlineColumnKey", *b.boolean(True))
        o.add("NSOutineViewStronglyReferencesItems", *b.boolean(False))
    return o, [(o, parent),
               _DeferredPairs(lambda: _table_pairs(b, el, id_map))]


def _popup(b, el, where, superview, id_map, parent=None):
    """<popUpButton> -> NSPopUpButton + NSPopUpButtonCell + NSMenu (probe ImportOPMLSheet)."""
    o = b.new("NSPopUpButton")
    o.add("NSNextResponder", *(b.ref(superview) if superview is not None else (N.NIL, None)))
    o.add("NSNibTouchBar", *(N.NIL, None))
    v, vt = _vflags(el, where)
    o.add("NSvFlags", vt, v)
    id_map[el.get("id")] = o
    o.add("NSFrame", *b.ref(b.string(_rect(el, "frame", where))))
    if superview is not None:
        o.add("NSSuperview", *b.ref(superview))
    o.add("NSViewWantsBestResolutionOpenGLSurface", *b.boolean(False))
    if _translates(el):
        o.add("NSDoNotTranslateAutoresizingMask", *b.boolean(False))
    cons_el = el.find("constraints")
    if cons_el is not None and cons_el.findall("constraint"):
        carr = b.new("NSArray")
        carr.add("NSInlinedValue", *b.boolean(False))
        els = I._constraint_order(el, cons_el.findall("constraint"), where, mac=True)
        cons = [_constraint(b, c, o, el.get("id"), id_map, {}, {}, where)
                if not (c.get("id") and c.get("id") in id_map)
                else id_map[c.get("id")] for c in els]
        b.cons_order[el.get("id")] = [c.get("id") for c in els]
        for con in cons:
            carr.add("UINibEncoderEmptyKey", *b.ref(con))
        o.add("NSViewConstraints", *b.ref(carr))
    h, v2 = el.get("horizontalHuggingPriority"), el.get("verticalHuggingPriority")
    if (h is not None and h != "750") or (v2 is not None and v2 != "750"):
        o.add("NSHuggingPriority",
              *b.ref(b.string("{%s, %s}" % (_fmt_g(h or 750), _fmt_g(v2 or 750)))))
    o.add("IBNSSafeAreaLayoutGuide", *(N.NIL, None))
    o.add("IBNSLayoutMarginsGuide", *(N.NIL, None))
    o.add("IBNSClipsToBounds", *b.int8(0))
    o.add("NSEnabled", *b.boolean(False))
    cell_el = el.find("popUpButtonCell[@key='cell']")
    if cell_el is None:
        raise I.XibError(f"<popUpButton> without popUpButtonCell ({where})")
    cell = _popup_cell(b, cell_el, o, where, id_map)
    o.add("NSCell", *b.ref(cell))
    id_map[cell_el.get("id")] = cell
    id_map[el.get("id") + "#cell"] = cell
    o.add("NSAllowsLogicalLayoutDirection", *b.boolean(not b.localize))
    o.add("NSControlSize", *b.int8(0))
    o.add("NSControlContinuous", *b.boolean(True))
    o.add("NSControlRefusesFirstResponder", *b.boolean(True))
    o.add("NSControlUsesSingleLineMode",
          *b.boolean(cell_el.get("usesSingleLineMode") != "YES"))
    align = cell_el.get("alignment", "left")
    if align not in CONTROL_ALIGN:
        raise I.XibError(f"alignment {align!r} not probed ({where})")
    o.add("NSControlTextAlignment", *b.int8(CONTROL_ALIGN[align]))
    lb = cell_el.get("lineBreakMode", "wordWrap")
    if lb not in LINE_BREAK:
        raise I.XibError(f"lineBreakMode {lb!r} not probed ({where})")
    o.add("NSControlLineBreakMode", *b.int8(LINE_BREAK[lb]))
    o.add("NSControlWritingDirection", N.INT64, -1)
    o.add("NSControlSendActionMask", *b.int8(4))
    o.add("IBNSShadowedSymbolConfiguration", *(N.NIL, None))
    return o, [(o, parent), (cell, o)]


def _popup_cell(b, el, control, where, id_map):
    o = b.new("NSPopUpButtonCell")
    ptype = el.get("type", "push")
    if ptype not in POPUP_CELL:
        raise I.XibError(f"popUpButtonCell type {ptype!r} not probed ({where})")
    cflags, bflags, bflags2, bezel, aux = POPUP_CELL[ptype]
    o.add("NSCellFlags", N.INT32, _i32(cflags) if cflags > 0x7FFFFFFF else cflags)
    lb = el.get("lineBreakMode", "wordWrap")
    if lb not in LINE_BREAK:
        raise I.XibError(f"lineBreakMode {lb!r} not probed ({where})")
    align = el.get("alignment")
    f2 = (TEXT_ALIGN[align] << 26 if align is not None else 0) | LINE_BREAK_FLAGS2[lb]
    o.add("NSCellFlags2", *int_fit(f2))
    menu_el = el.find("menu[@key='menu']")
    if menu_el is None:
        raise I.XibError(f"<popUpButtonCell> without menu ({where})")
    items = menu_el.find("items")
    if items is None or not len(items):
        raise I.XibError(f"<menu> without items ({where})")
    sel_id = el.get("selectedItem")
    sel_el = next((m for m in items if m.get("id") == sel_id), items[0])
    # NSContents is always a plain string, even in .lproj outputs (probe
    # AddFeedSheet golden [25] vs item titles)
    o.add("NSContents", *b.ref(b.string(sel_el.get("title", ""))))
    fd = el.find("font[@key='font']")
    if fd is None:
        raise I.XibError(f"<popUpButtonCell> without <font> ({where})")
    o.add("NSSupport", *b.ref(b.font(fd, where)))
    o.add("NSControlView", *b.ref(control))
    o.add("NSButtonFlags", *int_fit(_i32(bflags)))
    o.add("NSButtonFlags2", *int_fit(bflags2))
    o.add("NSBezelStyle", *b.int8(bezel))
    o.add("NSAlternateContents", *b.ref(b.string("")))
    o.add("NSKeyEquivalent", *b.ref(b.string("")))
    o.add("NSPeriodicDelay", N.INT16, 400)
    o.add("NSPeriodicInterval", *b.int8(75))
    o.add("NSAuxButtonType", *b.int8(aux))
    late_menu = _Late()
    sel = _menu_item(b, sel_el, late_menu, o, where)
    o.add("NSMenuItem", *b.ref(sel))
    o.add("NSMenuItemRespectAlignment", *b.boolean(False))
    menu = b.new("NSMenu")
    late_menu.obj = menu
    o.add("NSMenu", *b.ref(menu))
    id_map[menu_el.get("id")] = menu
    id_map[sel_el.get("id")] = sel
    if el.get("pullsDown") is not None:
        # probe TimelineContainerView [60]: pullsDown="YES" archives
        # NSSelectedIndex=-1 + NSPullDown=false
        o.add("NSSelectedIndex", *int_fit(-1))
        o.add("NSPullDown", *b.boolean(False))
    else:
        # probe GeneralPreferencesView [36] (jMV index 1): selected item's
        # index archives between NSMenu and NSPreferredEdge, omitted at 0
        # ([75]/[144] index 0 -> no key)
        idx = list(items).index(sel_el)
        if idx:
            o.add("NSSelectedIndex", *int_fit(idx))
    o.add("NSPreferredEdge", *b.int8(1))
    o.add("NSUsesItemFromMenu", *b.boolean(False))
    o.add("NSAltersState", *b.boolean(False))
    o.add("NSArrowPosition", *b.int8(2))
    # menu shell + remaining items in document order (probe ImportOPMLSheet)
    menu.add("NSTitle", *b.ref(b.string("")))
    iarr = b.new("NSMutableArray")
    iarr.add("NSInlinedValue", *b.boolean(False))
    menu.add("NSMenuItems", *b.ref(iarr))
    b.images = getattr(b, "images", {})
    for m in items:
        if m is sel_el:
            iarr.add("UINibEncoderEmptyKey", *b.ref(sel))
            continue
        item = _menu_item(b, m, menu, o, where)
        id_map[m.get("id")] = item
        iarr.add("UINibEncoderEmptyKey", *b.ref(item))
    return o
