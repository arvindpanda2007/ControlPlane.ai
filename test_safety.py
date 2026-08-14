from controlplane.safety import SafetyViolation, check_output


safe_text = "Customers can request a refund within 30 days."

check_output(safe_text)

print("SAFE TEST PASSED")


unsafe_text = "Contact john@example.com for the customer's SSN: 123-45-6789."

try:
    check_output(unsafe_text)
except SafetyViolation as error:
    print("BLOCKED TEST PASSED")
    print(error)