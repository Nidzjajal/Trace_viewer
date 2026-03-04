

def test_api_get(playwright):
    request =playwright.request.new_context()
    response=request.get("https://reqres.in/api/users?page=2")
    assert response.status==200
    assert response.ok ==True
    json_data=response.json()
    print(json_data)
    assert json_data["id"]==2
    request.dispose()
    