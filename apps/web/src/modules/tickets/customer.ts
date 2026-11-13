/** A customer picked for a ticket: an existing contact (`id`) or a new one by e-mail address or phone. */
export interface PickedCustomer {
  id?: string
  email?: string
  name?: string
  phone?: string
  label: string
}
