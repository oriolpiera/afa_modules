/** @odoo-module **/

document.addEventListener('DOMContentLoaded', () => {
    const form = document.querySelector('.afa-membership-form form');
    if (!form) {
        return;
    }

    const studentList = form.querySelector('#student-list');
    const addStudentButton = form.querySelector('#add-student');
    const membershipDetails = form.querySelector('#membership-details');
    const ibanInput = form.querySelector('#iban');
    const mandateInput = form.querySelector('#mandate-accepted');

    const updateMembershipFields = () => {
        const wantsMembership = form.querySelector('#membership-yes').checked;
        membershipDetails.hidden = !wantsMembership;
        ibanInput.required = wantsMembership;
        mandateInput.required = wantsMembership;
        if (!wantsMembership) {
            ibanInput.value = '';
            mandateInput.checked = false;
        }
    };

    form.querySelectorAll('input[name="wants_membership"]').forEach((input) => {
        input.addEventListener('change', updateMembershipFields);
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
        remove.className = 'btn btn-link text-danger col-12 text-start';
        remove.textContent = 'Elimina aquest alumne';
        remove.addEventListener('click', () => row.remove());
        row.append(remove);
        studentList.append(row);
    });

    updateMembershipFields();
});
