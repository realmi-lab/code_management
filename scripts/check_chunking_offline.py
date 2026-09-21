"""Run inside the backend image with docker --network none; no data writes."""
import asyncio
import json
from app.services.chunking.recursive import RecursiveChunking
from app.services.chunking.header import SectionHeaderChunking


async def main():
    checks = []
    for language, sentence in [('en', 'This is synthetic sentence number {}.'),
                               ('ko', '이 문장은 합성 자료이며 {}번째 안내 문장입니다.')]:
        text = ' '.join(sentence.format(i) for i in range(80))
        zero = await RecursiveChunking(680, 0).chunk(text)
        overlap = await RecursiveChunking(680, 340).chunk(text)
        assert len(zero) > 1 and len(overlap) > len(zero)
        assert all(chunk.content for chunk in zero + overlap)
        header = await SectionHeaderChunking(680, 0).chunk('# Synthetic\n' + text, {'file_type': 'md'})
        assert len(header) > 1 and all(chunk.content.startswith('[# Synthetic]') for chunk in header)
        checks.append({'language': language, 'zero_overlap_chunks': len(zero),
                       'half_overlap_chunks': len(overlap), 'header_chunks': len(header)})
    print(json.dumps({'passed': True, 'real_haystack_nltk_splitter': True,
                      'external_inference': False, 'production_data_written': False, 'checks': checks}))


if __name__ == '__main__':
    asyncio.run(main())
