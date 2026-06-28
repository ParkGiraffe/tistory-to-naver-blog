# 사용목적
Tistory에 작성한 글을 네이버블로그로 이동하기 위한 스크립트입니다.

Tistory의 글을 네이버블로그에 그대로 복사 후 붙여넣으면, 이미지를 거부하는 문제가 있습니다.

이 스크립트는 Tistory의 글을 파싱하여, 이미지를 다운로드하고, 네이버블로그에 그대로 복사하는 역할을 합니다.



# 사용방법
## 터미널모드
1. 터미널에서 python run_migration.py와 함께 Tistory Post URL을 입력합니다.
```bash
python run_migration.py <Tistory Post URL>
```

2. Auto Mode와 Manual Mode 중 하나를 선택합니다.
- 1. Auto Mode: 네이버블로그 에디터에 커서를 foucs하면, 순차적으로 글과 사진을 붙여넣습니다.
- 2. Manual Mode: 각 글과 사진을 CLI에서 확인하고, 붙여넣습니다.


## GUI 모드
### build
```bash
./build_mac.sh
```

1. TistoryMigrator.app을 실행합니다.
2. Tistory Post URL을 입력합니다.
3. Auto Mode와 Manual Mode 중 하나를 선택합니다.
- 1. Auto Mode: 네이버블로그 에디터에 커서를 foucs하면, 순차적으로 글과 사진을 붙여넣습니다.
- 2. Manual Mode: 각 글과 사진을 CLI에서 확인하고, 붙여넣습니다.

