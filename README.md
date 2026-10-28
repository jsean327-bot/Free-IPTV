# JoyLists

قوائم M3U مجانية وقانونية تتحدث كل يوم تلقائياً:

- **قنوات مباشرة** من كل الدول (iptv-org + Free-TV)، الدول العربية أول، وكل رابط مفحوص.
- **أفلام ومسلسلات كلاسيكية ورسوم ووثائقيات** من أرشيف الإنترنت (ملكية عامة).
- **إذاعات** من radio-browser.

## الروابط

العربية: https://raw.githubusercontent.com/jsean327-bot/Free-IPTV/lists/arabic_tv.m3u

كل شي: https://raw.githubusercontent.com/jsean327-bot/Free-IPTV/lists/all_in_one.m3u
## التحديث

- يتحدث تلقائياً كل يوم الساعة 5:37 الصبح بتوقيت الخليج.
- للتحديث الحين: **Actions** ← **Update free lists** ← **Run workflow**.
- أول تشغيل ياخذ وقت أطول (ممكن ساعة أو ساعتين) لأنه ينزل مكتبة الأفلام كاملة. بعده أسرع بكثير.

## روابط أقصر (اختياري)

**Settings** ← **Pages** ← تحت Branch اختر `lists` و `/ (root)` ← **Save**.
بعدها يشتغل الرابط القصير: `https://<اسم-الحساب>.github.io/<اسم-المستودع>/arabic_tv.m3u`

## إذا وقف التحديث

GitHub يوقف المهام اليومية إذا ما صار أي نشاط في المستودع 60 يوم. إذا شفت رسالة بهذا في تبويب **Actions**، اضغط **Enable workflow**.

## تشغيله على الكمبيوتر

`python free_media_builder.py --help` يعرض كل الخيارات.
