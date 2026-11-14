"""Source-derived state-machine trace, not a GUI/in-process integration test.
Mirrors cursor/page bookkeeping in src/ui/chat/codex/history.rs at pinned HEAD.
Rows are item identities to expose discontinuity when the live tail advances.
"""
from collections import deque
archive = list(range(451, 501))
page_rows = deque([50])
cursor_chain = [None]
newest_page = oldest_page = 0
# Reading paused. First request searches for anchor451 in current server pages,
# skips new501..550, finds451 at start of451..500 and requests older401..450.
for index, before in [(1,451),(2,401),(3,351),(4,301)]:
    page = list(range(before-50,before))
    while len(cursor_chain) <= index:
        cursor_chain.append(None)
    cursor_chain[index] = before
    if len(cursor_chain) == index+1:
        cursor_chain.append(before-50)
    archive = page + archive
    page_rows.appendleft(len(page))
    oldest_page = index
    while len(archive) > 200:
        count=page_rows.pop()
        archive=archive[:-count]
        newest_page += 1
assert archive == list(range(251,451))
assert newest_page == 1
# Meanwhile server has600 items. User scrolls newer from original page1.
index = newest_page - 1
requested = cursor_chain[index]  # Actual branch: index0 maps to None.
assert requested is None
returned = list(range(551,601)) # thread/items/list(cursor:null,limit50,desc)
archive += returned
page_rows.append(len(returned))
newest_page=index
while len(archive)>200:
    count=page_rows.popleft(); archive=archive[count:]; oldest_page -= 1
missing = sorted(set(range(min(archive),max(archive)+1))-set(archive))
print(f"Newer selected index={index}, cursor={requested}")
print(f"Visible archive starts={archive[0]}, ends={archive[-1]}")
print(f"Skipped identities={missing[0]}..{missing[-1]} ({len(missing)} rows)")
assert missing == list(range(451,551))
