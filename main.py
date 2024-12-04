from fastapi import FastAPI, File, UploadFile, HTTPException
import os
import shutil
import requests
from unittest.mock import patch
from pydantic import BaseModel
import xml.etree.ElementTree as ET

# FastAPI 애플리케이션 생성
app = FastAPI()

# AI 서버 URL 및 의약품 정보 API URL
AI_SERVER_URL = "http://fake-ai-server/identify-medicine"
MEDICINE_INFO_API_URL = (
    "http://apis.data.go.kr/1471000/DURPrdlstInfoService03/getDurPrdlstInfoList03"
)


# 모킹 함수 (테스트 시)
def mock_ai_server_response(*args, **kwargs):
    return {
        "status_code": 200,
        "json": lambda: {"medicine_name": "타이레놀"},  # 예시 의약품 이름 반환
    }


# 의약품 정보 요청 모델
class ItemRequest(BaseModel):
    api_key: str
    item_name: str
    page_number: int = 1
    num_of_rows: int = 1
    response_type: str = "xml"  # 기본값을 xml로 설정


@app.post("/upload-medicine-photo/")
async def upload_medicine_photo(file: UploadFile = File(...)):
    try:
        # temp 디렉토리가 없으면 생성
        os.makedirs("temp", exist_ok=True)

        # 업로드된 이미지를 로컬 파일로 저장
        file_path = f"temp/{file.filename}"
        print(f"Saving file to: {file_path}")
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # AI 서버에 이미지 파일을 전송하는 부분을 모킹 (테스트 시)
        with patch("requests.post", side_effect=mock_ai_server_response):
            files = {"file": open(file_path, "rb")}
            ai_response = requests.post(AI_SERVER_URL, files=files)
            print(f"AI Response: {ai_response}")

        # AI 서버에서 받은 의약품 이름을 사용하여 의약품 정보 API 호출
        medicine_name = ai_response["json"]().get("medicine_name")
        print(f"Identified Medicine: {medicine_name}")

        # 의약품 정보 API 호출
        api_key = "YOUR_API_KEY"  # 실제 API 키를 여기에 입력
        item_request = ItemRequest(api_key=api_key, item_name=medicine_name)

        # 의약품 정보 가져오기
        item_info = get_item_info(item_request)

        return item_info

    except Exception as e:
        print(f"Error occurred: {e}")
        return {"error": "An internal error occurred", "details": str(e)}


# XML 데이터를 처리하는 함수
def parse_xml_response(xml_data):
    try:
        # XML 데이터를 파싱
        root = ET.fromstring(xml_data)

        # XML 내에서 필요한 데이터 추출
        items = root.findall(".//item")
        if not items:
            raise HTTPException(status_code=404, detail="No items found")

        item = items[0]  # 첫 번째 아이템을 사용
        nb_doc_id = (
            item.find("NB_DOC_ID").text if item.find("NB_DOC_ID") is not None else None
        )
        insert_file = (
            item.find("INSERT_FILE").text
            if item.find("INSERT_FILE") is not None
            else None
        )
        item_name = (
            item.find("ITEM_NAME").text if item.find("ITEM_NAME") is not None else None
        )
        company_name = (
            item.find("ENTP_NAME").text if item.find("ENTP_NAME") is not None else None
        )

        if not nb_doc_id and not insert_file:
            raise HTTPException(status_code=404, detail="PDF URLs not found")

        result = {
            "pdf_viewer_url": nb_doc_id,
            "pdf_download_url": insert_file,
            "item_name": item_name,
            "company_name": company_name,
        }

        print(f"Parsed XML Result: {result}")

        return result
    except ET.ParseError as e:
        print(f"XML Parse Error: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Invalid XML response from external API: {str(e)}"
        )


# 의약품 정보 API 호출 함수 (xml 응답 처리)
@app.post("/get_item_info")
def get_item_info(request: ItemRequest):
    url = MEDICINE_INFO_API_URL
    params = {
        "serviceKey": request.api_key,
        "itemName": request.item_name,
        "pageNo": request.page_number,
        "numOfRows": request.num_of_rows,
        "type": request.response_type,  # 여기서 xml로 요청
    }

    response = requests.get(url, params=params)
    print(f"Response Status Code: {response.status_code}")
    print(f"Response Content: {response.content}")

    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"API request failed: {response.text}",
        )

    # XML 데이터를 처리
    return parse_xml_response(response.content)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
