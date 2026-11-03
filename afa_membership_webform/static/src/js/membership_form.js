/** @odoo-module **/

const initializeMembershipForm = () => {
    const form = document.querySelector('.afa-membership-form form');
    if (!form) {
        return;
    }

    const studentList = form.querySelector('#student-list');
    const addStudentButton = form.querySelector('#add-student');
    const accountHolderInput = form.querySelector('#bank_account_holder_name');
    const ibanInput = form.querySelector('#iban');
    const mandateInput = form.querySelector('#mandate-accepted');

    const updateMembershipFields = () => {
        const wantsMembership = form.querySelector('#membership-yes').checked;
        const needsMandate = wantsMembership || mandateInput.checked;
        accountHolderInput.required = needsMandate;
        ibanInput.required = needsMandate;
        mandateInput.required = wantsMembership;
    };

    form.querySelectorAll('input[name="wants_membership"]').forEach((input) => {
        input.addEventListener('change', updateMembershipFields);
    });
    mandateInput.addEventListener('change', updateMembershipFields);

    studentList.addEventListener('click', (event) => {
        const removeButton = event.target.closest('.remove-student');
        if (removeButton) {
            removeButton.closest('.student-row').remove();
        }
    });

    addStudentButton.addEventListener('click', () => {
        const template = studentList.querySelector('.student-row');
        const row = template.cloneNode(true);
        row.querySelectorAll('input').forEach((input) => {
            input.value = '';
        });
        row.querySelector('select').selectedIndex = 0;
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'btn btn-link text-danger text-start remove-student';
        remove.textContent = 'Elimina aquest alumne';
        row.append(remove);
        studentList.append(row);
    });

    updateMembershipFields();
};

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeMembershipForm, {once: true});
} else {
    initializeMembershipForm();
}
