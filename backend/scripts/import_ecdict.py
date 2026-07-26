"""导入 ECDICT(MIT 许可·英汉词典,~77 万词条)到 dict_ecdict 表。

dict_ecdict 是补 vocabulary_words 释义/音标缺口的数据源(dict 优先 + LLM 兜底),
**每环境各自导入一次,不进 content_seed**(免把 63MB 塞进生产种子)。表结构由迁移
m200_dict_ecdict 建;本脚本只灌数据(幂等:TRUNCATE 后重灌)。

用法(backend 目录下,已加载 .env):
    python scripts/import_ecdict.py [/path/to/ecdict.csv]
不传路径则自动从 GitHub 下载(skywind3000/ECDICT,MIT)。
"""
import asyncio
import os
import sys
import urllib.request

from app.core.database import _async_session_factory

_CSV_URL = "https://raw.githubusercontent.com/skywind3000/ECDICT/master/ecdict.csv"
_STG_COLS = ["word", "phonetic", "definition", "translation", "pos", "collins",
             "oxford", "tag", "bnc", "frq", "exchange", "detail", "audio"]


async def main() -> None:
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/ecdict.csv"
    if not os.path.exists(csv_path):
        print(f"下载 ECDICT → {csv_path} …")
        urllib.request.urlretrieve(_CSV_URL, csv_path)
    size_mb = os.path.getsize(csv_path) // (1024 * 1024)
    print(f"CSV: {csv_path} ({size_mb}MB)")

    async with _async_session_factory() as s:
        conn = await s.connection()
        raw = await conn.get_raw_connection()
        ap = raw.driver_connection            # asyncpg 原生连接(COPY 用)
        await ap.execute("""
            CREATE TABLE IF NOT EXISTS dict_ecdict (
                id BIGSERIAL PRIMARY KEY, word VARCHAR(128) NOT NULL,
                word_lower VARCHAR(128) NOT NULL, phonetic VARCHAR(128),
                translation TEXT, tag VARCHAR(64));
            CREATE INDEX IF NOT EXISTS ix_dict_ecdict_lower ON dict_ecdict (word_lower);
        """)
        await ap.execute("TRUNCATE dict_ecdict")
        await ap.execute("""
            CREATE TEMP TABLE stg (word text,phonetic text,definition text,translation text,
                pos text,collins text,oxford text,tag text,bnc text,frq text,
                exchange text,detail text,audio text) ON COMMIT DROP""")
        with open(csv_path, "rb") as f:
            await ap.copy_to_table("stg", source=f, columns=_STG_COLS,
                                   format="csv", header=True)
        await ap.execute("""
            INSERT INTO dict_ecdict (word, word_lower, phonetic, translation, tag)
            SELECT word, lower(word), NULLIF(phonetic,''), NULLIF(translation,''), NULLIF(tag,'')
            FROM stg WHERE translation IS NOT NULL AND translation<>''""")
        n = await ap.fetchval("SELECT count(*) FROM dict_ecdict")
        print(f"✓ dict_ecdict 导入完成:{n} 行")


if __name__ == "__main__":
    asyncio.run(main())
